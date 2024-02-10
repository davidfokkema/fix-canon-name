import asyncio

import rich
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Footer, Header, Label, ListItem, ListView
from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

SERVICE = "_printer._tcp.local."


class Printer(ListItem):
    def __init__(self, printer_name: str, server: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.printer_name = printer_name
        self.server = server

    def compose(self) -> ComposeResult:
        yield Label(self.printer_name.removesuffix("." + SERVICE))


class PrinterList(ListView):
    BINDINGS = [("r", "reload", "Reload")]

    browser: AsyncServiceBrowser | None = None

    class New(Message):
        """New printer found."""

        __slots__ = ["printer_name", "server"]

        def __init__(self, name: str, server: str) -> None:
            super().__init__()
            self.printer_name = name
            self.server = server

        def __rich_repr__(self) -> rich.repr.Result:
            yield "printer_name", self.printer_name
            yield "server", self.server

    def on_mount(self) -> None:
        self.browse_services()

    @on(New)
    def add_printer(self, event: New) -> None:
        self.append(Printer(event.printer_name, event.server))

    def browse_services(self):
        def on_service_state_change(
            zeroconf: Zeroconf,
            service_type: str,
            name: str,
            state_change=ServiceStateChange,
        ) -> None:
            asyncio.create_task(get_service_info(zeroconf, service_type, name))

        async def get_service_info(
            zeroconf: Zeroconf, service_type: str, name: str
        ) -> None:
            info = AsyncServiceInfo(service_type, name)
            await info.async_request(zeroconf, 3000)
            self.post_message(self.New(name, info.server))

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
