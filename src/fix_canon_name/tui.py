import asyncio
import hashlib
import re

import rich
from selenium import webdriver
from selenium.webdriver.common.by import By
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
)
from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

SERVICE = "_printer._tcp.local."
RE_NAME = "(?P<name>.*?)(?= \([a-f0-9]{2}:[a-f0-9]{2}:[a-f0-9]{2}\))"


class FixPrinterScreen(ModalScreen):

    class StatusUpdate(Message):
        def __init__(self, msg: str, advance: bool = True) -> None:
            super().__init__()
            self.msg = msg
            self.advance = advance

    class Completed(Message):
        pass

    class Failed(Message):
        msg: str | None

        def __init__(self, msg: str | None = None) -> None:
            super().__init__()
            self.msg = msg

    def __init__(self, server: str, pin_code: str, new_name: str) -> None:
        super().__init__()
        self.server = server
        self.pin_code = pin_code
        self.new_name = new_name

    def compose(self) -> ComposeResult:
        with Vertical():
            with Center():
                yield Label(id="status_msg")
            with Center():
                yield ProgressBar(total=4, show_eta=False, id="progress")
            with Center():
                yield Button(label="Cancel", variant="error", id="cancel")

    def on_mount(self) -> None:
        self.reset_name_through_browser()

    @on(StatusUpdate)
    def update_message(self, event: StatusUpdate) -> None:
        self.query_one("#status_msg").update(event.msg)
        if event.advance:
            self.query_one(ProgressBar).advance(1)

    @on(Completed)
    def finish_task(self) -> None:
        self.query_one(ProgressBar).advance(1)
        self.notify("Reset done.")
        self.dismiss(True)

    @on(Failed)
    def exit_with_error(self, event: Failed) -> None:
        self.notify(event.msg, severity="error")
        self.dismiss(False)

    @on(Button.Pressed, "#cancel")
    def cancel_task(self) -> None:
        self.notify("Canceled.", severity="warning")
        self.dismiss(False)

    @work(thread=True)
    def reset_name_through_browser(self) -> None:
        self.post_message(self.StatusUpdate("Starting web driver...", advance=False))
        options = webdriver.FirefoxOptions()
        options.add_argument("--headless")
        options.accept_insecure_certs = True
        with webdriver.Firefox(options=options) as driver:
            self.post_message(
                self.StatusUpdate("Connecting to printer...", advance=False)
            )
            driver.get(f"https://{self.server}/login.html")
            driver.find_element(By.ID, "i0012A").click()
            driver.find_element(By.ID, "i2101").send_keys(self.pin_code)
            self.post_message(self.StatusUpdate("Logging in..."))
            driver.find_element(By.ID, "submitButton").click()
            if not driver.current_url.endswith("portal_top.html"):
                self.post_message(self.Failed(msg="Login failed, incorrect PIN?"))
                return

            self.post_message(self.StatusUpdate("Loading Airprint settings..."))
            driver.get(f"https://{self.server}/m_network_airprint_edit.html")
            name_element = driver.find_element(By.ID, "i2072")
            name_element.clear()
            name_element.send_keys(self.new_name)
            self.post_message(self.StatusUpdate("Setting new printer name..."))
            driver.find_element(By.ID, "submitButton").click()
        self.post_message(self.Completed())


class PinCodeScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        yield Input(placeholder="Printer's PIN code", password=True)

    @on(Input.Submitted)
    def send_pin_code(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)


class NewNameScreen(ModalScreen):
    def __init__(self, current_name: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.current_name = current_name

    def compose(self) -> ComposeResult:
        if match := re.match(RE_NAME, self.current_name):
            new_name = match.group("name")
        else:
            new_name = self.current_name.split("._printer")[0]
        yield Input(value=new_name)

    @on(Input.Submitted)
    def send_new_name(self, event: Input.Submitted) -> None:
        if not (new_name := event.value):
            new_name = self.current_name
        self.dismiss(new_name)


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
        new_name = await self.app.push_screen_wait(
            NewNameScreen(event.item.printer_name)
        )
        pin_code = await self.app.push_screen_wait(PinCodeScreen())
        await self.app.push_screen_wait(
            FixPrinterScreen(event.item.server, pin_code, new_name)
        )

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


class FixCanonNameApp(App[None]):
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+s", "save_screenshot", "Screenshot", priority=True),
    ]

    CSS_PATH = "app.tcss"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield PrinterList()

    def action_quit(self) -> None:
        self.exit()

    def action_save_screenshot(self) -> None:
        path = self.save_screenshot()
        self.notify(f"Saved screenshot to {path}")


app = FixCanonNameApp()


def main():
    app.run()


if __name__ == "__main__":
    main()
