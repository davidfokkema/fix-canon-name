import asyncio
import hashlib
import re

import rich
from selenium import webdriver
from selenium.webdriver.common.by import By
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView
from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

SERVICE = "_printer._tcp.local."
RE_NAME = "(?P<name>.*?) \([0-9a-f:]{8}\)"


class PinCodeScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        yield Input(placeholder="Printer's PIN code", password=True)

    @on(Input.Submitted)
    def send_pin_code(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


class Printer(ListItem):
    def __init__(self, printer_name: str, server: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.printer_name = printer_name
        self.server = server

    def compose(self) -> ComposeResult:
        yield Label(self.printer_name.removesuffix("." + SERVICE))


class PrinterList(ListView):
    BINDINGS = [("r", "reload", "Reload")]
    idx = 0
    browser: AsyncServiceBrowser | None = None

    class PrinterMessage(Message):

        __slots__ = ["printer_name", "server"]

        def __init__(self, name: str, server: str) -> None:
            super().__init__()
            self.printer_name = name
            self.server = server

        def __rich_repr__(self) -> rich.repr.Result:
            yield "printer_name", self.printer_name
            yield "server", self.server

    class NewPrinter(PrinterMessage):
        """New printer found."""

    class RemovedPrinter(PrinterMessage):
        """Printer must be removed."""

    def on_mount(self) -> None:
        self.browse_services()

    @on(NewPrinter)
    def add_printer(self, event: NewPrinter) -> None:
        hash = self.hash_name(event.printer_name)
        self.append(Printer(event.printer_name, event.server, id=hash))

    @on(RemovedPrinter)
    def remove_printer(self, event: RemovedPrinter) -> None:
        hash = self.hash_name(event.printer_name)
        widget = self.query_one("#" + hash)
        widget.remove()

    def hash_name(self, name: str) -> str:
        return "P" + hashlib.md5(name.encode()).hexdigest()

    @on(ListView.Selected)
    @work()
    async def fix_printer_name(self, event: ListView.Selected) -> None:
        pin_code = await self.app.push_screen_wait(PinCodeScreen())
        self.notify("Resetting...")
        self.reset_name_through_browser(event.item.server, pin_code)
        self.notify("Reset done.")

    def browse_services(self):
        def on_service_state_change(
            zeroconf: Zeroconf,
            service_type: str,
            name: str,
            state_change=ServiceStateChange,
        ) -> None:
            asyncio.create_task(
                get_service_info(zeroconf, service_type, name, state_change)
            )

        async def get_service_info(
            zeroconf: Zeroconf,
            service_type: str,
            name: str,
            state_change: ServiceStateChange,
        ) -> None:
            info = AsyncServiceInfo(service_type, name)
            await info.async_request(zeroconf, 3000)
            match state_change:
                case ServiceStateChange.Added:
                    self.post_message(self.NewPrinter(name, info.server))
                case ServiceStateChange.Removed:
                    self.post_message(self.RemovedPrinter(name, info.server))

        self.zeroconf = Zeroconf()
        self.browser = AsyncServiceBrowser(
            self.zeroconf,
            SERVICE,
            handlers=[on_service_state_change],
        )

    async def action_reload(self) -> None:
        if self.browser is not None:
            await self.browser.async_cancel()
            self.browser = None
            self.clear()
            self.browse_services()

    @work(thread=True)
    def reset_name_through_browser(self, server: str, pin_code: str) -> None:
        options = webdriver.FirefoxOptions()
        options.add_argument("--headless")
        options.accept_insecure_certs = True
        with webdriver.Firefox(options=options) as driver:
            driver.get(f"https://{server}/login.html")
            driver.find_element(By.ID, "i0012A").click()
            driver.find_element(By.ID, "i2101").send_keys(pin_code)
            driver.find_element(By.ID, "submitButton").click()

            driver.get(f"https://{server}/m_network_airprint_edit.html")
            name_element = driver.find_element(By.ID, "i2072")
            current_name = name_element.get_attribute("value")
            if match := re.match(RE_NAME, current_name):
                printer_name = match.group("name")
                name_element.clear()
                name_element.send_keys(printer_name)
                driver.find_element(By.ID, "submitButton").click()


class FixCanonNameApp(App[None]):
    BINDINGS = [Binding("q", "quit", "Quit", priority=True)]

    CSS_PATH = "app.tcss"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield PrinterList()

    def action_quit(self) -> None:
        self.exit()


app = FixCanonNameApp()


def main():
    app.run()


if __name__ == "__main__":
    main()
