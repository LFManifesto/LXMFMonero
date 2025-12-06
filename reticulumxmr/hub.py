#!/usr/bin/env python3
"""
ReticulumXMR Hub Server
Runs on Pi - provides Monero RPC access over Reticulum

Cold Signing Mode:
- Hub has view-only wallet (can see balance, create unsigned tx)
- Client has spending keys (signs transactions locally)
- Hub broadcasts signed transactions
"""
import RNS
import time
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

from .rpc_protocol import (
    register_message_types,
    ModeSelectionMessage,
)
from .hub_cold_signing import HubColdSigningSession
from .view_key_protocol import register_view_key_messages
from .config import Config

APP_NAME = "reticulumxmr"


class ReticulumXMRHub:
    """Main hub server for cold signing mode"""

    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.sessions = []

        # Initialize Reticulum
        logger.info("Initializing Reticulum...")
        self.reticulum = RNS.Reticulum()

        # Load or create identity
        identity_path = self.config.CONFIG_DIR / "hub_identity"
        if identity_path.exists():
            self.identity = RNS.Identity.from_file(str(identity_path))
            logger.info(f"Loaded identity from {identity_path}")
        else:
            self.identity = RNS.Identity()
            self.identity.to_file(str(identity_path))
            logger.info(f"Created new identity at {identity_path}")

        # Create destination
        self.destination = RNS.Destination(
            self.identity,
            RNS.Destination.IN,
            RNS.Destination.SINGLE,
            APP_NAME,
            "hub"
        )

        # Set up link callback
        self.destination.set_link_established_callback(self._link_established)

        # Wallet RPC URL for cold signing
        rpc_host = self.config.get("monero_rpc_host", "127.0.0.1")
        rpc_port = self.config.get("monero_rpc_port", 18085)
        self.wallet_rpc_url = f"http://{rpc_host}:{rpc_port}/json_rpc"

        logger.info("=" * 60)
        logger.info("ReticulumXMR Hub Server Started")
        logger.info("=" * 60)
        logger.info(f"Destination: {RNS.prettyhexrep(self.destination.hash)}")
        logger.info(f"Wallet RPC:  {self.wallet_rpc_url}")
        logger.info("=" * 60)

    def _link_established(self, link: RNS.Link):
        """Called when client establishes link"""
        try:
            remote_identity = link.get_remote_identity()
            if remote_identity:
                client_id = RNS.prettyhexrep(remote_identity)
            else:
                client_id = RNS.prettyhexrep(link.hash)

            logger.info(f"Link established with {client_id}")

            channel = link.get_channel()
            if not channel:
                logger.error("Could not get channel from link")
                return

            # Register all message types
            try:
                register_message_types(channel)
                register_view_key_messages(channel)
            except Exception as e:
                logger.error(f"Could not register message types: {e}")
                return

            # Session holder
            pending = {
                'link': link,
                'channel': channel,
                'client_id': client_id,
                'session': None
            }

            def create_session(mode: str):
                """Create cold signing session"""
                logger.info(f"Creating session for mode: {mode}")

                if mode == ModeSelectionMessage.MODE_COLD_SIGNING:
                    session = HubColdSigningSession(link, self.wallet_rpc_url)
                    pending['session'] = session
                    self.sessions.append(session)
                    logger.info("Cold signing session created")
                else:
                    logger.warning(f"Unsupported mode: {mode}, using cold signing")
                    session = HubColdSigningSession(link, self.wallet_rpc_url)
                    pending['session'] = session
                    self.sessions.append(session)

            def initial_message_handler(message):
                """Handle first message to create session"""
                msg_type = type(message).__name__
                logger.debug(f"Received message: {msg_type}")

                try:
                    if isinstance(message, ModeSelectionMessage):
                        logger.info(f"Mode selection: {message.mode}")
                        try:
                            channel.remove_message_handler(initial_message_handler)
                        except Exception:
                            pass
                        create_session(message.mode)
                        return True
                    else:
                        # Any other message - create cold signing session
                        if pending['session'] is None:
                            logger.info(f"Non-mode message, creating cold signing session")
                            try:
                                channel.remove_message_handler(initial_message_handler)
                            except Exception:
                                pass
                            create_session(ModeSelectionMessage.MODE_COLD_SIGNING)
                        return False

                except Exception as e:
                    logger.error(f"Error in message handler: {e}")
                    return False

            channel.add_message_handler(initial_message_handler)
            logger.info("Waiting for client mode selection...")

            def on_link_closed(closed_link):
                logger.info(f"Link closed for {client_id}")
                if pending['session']:
                    if hasattr(pending['session'], 'close'):
                        pending['session'].close()
                    if pending['session'] in self.sessions:
                        self.sessions.remove(pending['session'])

            link.set_link_closed_callback(on_link_closed)

        except Exception as e:
            logger.error(f"Error in _link_established: {e}")

    def run(self):
        """Run hub server"""
        logger.info("Waiting for client connections...")
        logger.info("Press Ctrl+C to stop")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            sys.exit(0)


def main():
    """Entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="ReticulumXMR Hub Server")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    hub = ReticulumXMRHub()
    hub.run()


if __name__ == "__main__":
    main()
