import asyncio

import rich
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Footer, Header, ListItem, ListView
from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo


class PrinterList(ListView):
    BINDINGS = [("r", "reload", "Reload")]

    browser: AsyncServiceBrowser | None = None

    class New(Message):
        """New printer found."""

        __slots__ = ["name", "server"]

        def __init__(self, name: str, server: str) -> None:
            super().__init__()
            self.name = name
            self.server = server

        def __rich_repr__(self) -> rich.repr.Result:
            yield "name", self.name
            yield "server", self.server

    def on_mount(self) -> None:
        self.browse_services()

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
            "_printer._tcp.local.",
            handlers=[on_service_state_change],
        )

    async def action_reload(self) -> None:
        if self.browser is not None:
            await self.browser.async_cancel()
            self.browser = None
            self.browse_services()


class FixCanonNameApp(App[None]):
    BINDINGS = [Binding("q", "quit", "Quit", priority=True)]

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
