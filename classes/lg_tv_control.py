"""
LG WebOS TV Control Module

This module provides a self-contained controller for interacting with LG WebOS TVs.
It handles authentication, token persistence, and retrieves the current HDMI input
to map to corresponding color commands for ambient lighting control.
"""

import json
import os
import socket
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from pywebostv.connection import WebOSClient
from pywebostv.controls import ApplicationControl


# Custom Exceptions
class LGTVError(Exception):
    """Base exception for LG TV control errors"""
    pass


class TVNotFoundError(LGTVError):
    """TV hostname cannot be resolved"""
    pass


class TVConnectionError(LGTVError):
    """Cannot connect to TV"""
    pass


class TVNotRegisteredError(LGTVError):
    """TV registration failed or not completed"""
    pass


class TVInputNotMappedError(LGTVError):
    """Current HDMI input has no color mapping"""
    pass


# Configuration
@dataclass
class LGTVConfig:
    """Configuration for LG TV control"""
    hostname: str
    token_file_path: str
    hdmi_color_map: Dict[str, str] = field(default_factory=dict)
    secure: bool = True

    @classmethod
    def default(cls, token_file_path: str = "./secrets/lgtoken.json"):
        """Create default configuration"""
        return cls(
            hostname="LGwebOSTV.dankurtz.local",
            token_file_path=token_file_path,
            hdmi_color_map={
                "com.webos.app.hdmi3": "ColorPC",
                "com.webos.app.hdmi1": "ColorAppleTV",
                "com.webos.app.hdmi4": "ColorPS4",
                "com.webos.app.hdmi5": "ColorNintendo"
            },
            secure=True
        )


# Model
@dataclass
class ColorCommandResult:
    """Result of getting color command from TV"""
    status: str
    commands: Optional[List[str]] = None
    message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        result = {"status": self.status}
        if self.commands:
            result["commands"] = self.commands
        if self.message:
            result["message"] = self.message
        return result


# Controller
class LGTVController:
    """Controller for LG WebOS TV operations"""

    def __init__(self, config: LGTVConfig):
        """
        Initialize LG TV Controller

        Args:
            config: LGTVConfig instance with TV settings
        """
        self.config = config
        self._token_store = {}
        self._load_token()

    def _load_token(self) -> None:
        """Load authentication token from file if it exists"""
        if os.path.exists(self.config.token_file_path):
            try:
                with open(self.config.token_file_path, 'r') as f:
                    self._token_store = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                # If token file is corrupted, start fresh
                self._token_store = {}

    def _save_token(self) -> None:
        """Save authentication token to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.config.token_file_path), exist_ok=True)
            with open(self.config.token_file_path, 'w') as f:
                json.dump(self._token_store, f)
        except IOError as e:
            raise LGTVError(f"Failed to save token: {e}")

    def _verify_hostname(self) -> None:
        """Verify that TV hostname can be resolved"""
        try:
            socket.gethostbyname(self.config.hostname)
        except socket.gaierror:
            raise TVNotFoundError(f"Cannot resolve hostname: {self.config.hostname}")

    def _connect_and_register(self) -> WebOSClient:
        """
        Connect to TV and handle registration

        Returns:
            WebOSClient instance

        Raises:
            TVConnectionError: If connection fails
            TVNotRegisteredError: If registration fails
        """
        try:
            client = WebOSClient(self.config.hostname, secure=self.config.secure)
            client.connect()
        except Exception as e:
            raise TVConnectionError(f"Failed to connect to TV: {e}")

        registered = False

        try:
            for status in client.register(self._token_store):
                if status == WebOSClient.PROMPTED:
                    print("Please accept the connection on the TV!")
                elif status == WebOSClient.REGISTERED:
                    print("Registration successful!")
                    registered = True

            # Save updated token store
            self._save_token()

            if not registered:
                raise TVNotRegisteredError("TV registration not completed")

            return client

        except Exception as e:
            if isinstance(e, TVNotRegisteredError):
                raise
            raise TVConnectionError(f"Registration failed: {e}")

    def _get_current_input(self, client: WebOSClient) -> str:
        """
        Get current HDMI input from TV

        Args:
            client: Connected WebOSClient instance

        Returns:
            Application ID string (e.g., "com.webos.app.hdmi3")
        """
        app_control = ApplicationControl(client)
        return app_control.get_current()

    def _map_input_to_color(self, input_id: str) -> str:
        """
        Map HDMI input ID to color command

        Args:
            input_id: Application ID from TV

        Returns:
            Color command string

        Raises:
            TVInputNotMappedError: If input has no mapping
        """
        if input_id not in self.config.hdmi_color_map:
            raise TVInputNotMappedError(
                f"No color mapping for input: {input_id}"
            )
        return self.config.hdmi_color_map[input_id]

    def get_color_command(self) -> ColorCommandResult:
        """
        Get color command based on current TV input

        This is the main public method that orchestrates the entire process:
        1. Verify TV is reachable
        2. Connect and register
        3. Get current input
        4. Map to color command
        5. Clean up connection

        Returns:
            ColorCommandResult with status and commands
        """
        client = None

        try:
            # Verify TV is reachable
            self._verify_hostname()

            # Connect and register
            client = self._connect_and_register()

            # Get current input
            input_id = self._get_current_input(client)

            # Map to color command
            color_command = self._map_input_to_color(input_id)

            return ColorCommandResult(
                status="success",
                commands=[color_command]
            )

        except TVNotFoundError as e:
            return ColorCommandResult(
                status="Error",
                message=f"TV not found: {e}"
            )

        except TVNotRegisteredError as e:
            return ColorCommandResult(
                status="Not Registered",
                message=str(e)
            )

        except TVInputNotMappedError as e:
            return ColorCommandResult(
                status="Error",
                message=str(e)
            )

        except (TVConnectionError, LGTVError) as e:
            return ColorCommandResult(
                status="Error",
                message=f"Could not connect to TV: {e}"
            )

        except Exception as e:
            # Catch-all for unexpected errors
            return ColorCommandResult(
                status="Error",
                message=f"Unexpected error: {e}"
            )

        finally:
            # Always close connection
            if client:
                try:
                    client.close()
                except:
                    pass

    def update_hdmi_mapping(self, hdmi_id: str, color_command: str) -> None:
        """
        Update or add HDMI to color mapping

        Args:
            hdmi_id: HDMI input ID (e.g., "com.webos.app.hdmi3")
            color_command: Color command to map to (e.g., "ColorPC")
        """
        self.config.hdmi_color_map[hdmi_id] = color_command

    def get_current_mappings(self) -> Dict[str, str]:
        """Get current HDMI to color mappings"""
        return self.config.hdmi_color_map.copy()
