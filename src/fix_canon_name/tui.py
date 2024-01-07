import asyncio

import rich
from textual.app import App, ComposeResult
from textual.message import Message
from textual.widgets import Footer, Header, ListItem, ListView
from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo


class PrinterList(ListView):
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
        print("Mounting...")
        self.browse_services()

    def browse_services(self):
        def on_service_state_change(
            zeroconf: Zeroconf,
            service_type: str,
            name: str,
            state_change=ServiceStateChange,
        ) -> None:
            asyncio.create_task(
                async_display_service_info(zeroconf, service_type, name)
            )

        async def async_display_service_info(
            zeroconf: Zeroconf, service_type: str, name: str
        ) -> None:
            info = AsyncServiceInfo(service_type, name)
            await info.async_request(zeroconf, 3000)
            self.post_message(self.New(name, info.server))
            print("Sending message...")

        self.zeroconf = Zeroconf()
        self.browser = AsyncServiceBrowser(
            self.zeroconf,
            "_printer._tcp.local.",
            handlers=[on_service_state_change],
        )


class FixCanonNameApp(App[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield PrinterList()


app = FixCanonNameApp()


def main():
    app.run()


if __name__ == "__main__":
    main()
