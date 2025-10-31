"""
Solar Blind Control Module

This module provides a self-contained controller for automated window blind control
based on sun position and weather conditions. It calculates solar altitude/azimuth
and determines when to raise or close blinds based on configurable watch areas.
"""

import datetime
import calendar
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any
from pysolar import solar


# Custom Exceptions
class SolarControlError(Exception):
    """Base exception for solar blind control errors"""
    pass


class InvalidSolarDataError(SolarControlError):
    """Invalid solar sensor data provided"""
    pass


class ConfigurationError(SolarControlError):
    """Invalid configuration parameters"""
    pass


# Configuration
@dataclass
class SolarBlindConfig:
    """Configuration for solar blind control"""
    latitude: float
    longitude: float
    timezone_name: str = "US/Pacific"

    # Watch area bounds (azimuth and altitude ranges)
    start_azimuth: float = 0.0
    end_azimuth: float = 360.0
    start_altitude: float = 0.0
    end_altitude: float = 90.0

    # Solar threshold settings
    solar_threshold: float = 100.0
    lower_altitude: float = 20.0
    upper_altitude: float = 60.0
    lower_altitude_percent: float = 0.5
    upper_altitude_percent: float = 1.0

    # Buffer settings
    change_buffer_duration_sec: int = 1800  # 30 minutes default

    # Control settings
    command_override: bool = False

    # Condition settings for closing blinds
    close_conditions: List[str] = field(default_factory=lambda: ["Cloudy"])

    @classmethod
    def default(cls, latitude: float = 45.46692, longitude: float = -122.79286):
        """Create default configuration for Portland, OR area"""
        return cls(
            latitude=latitude,
            longitude=longitude,
            timezone_name="US/Pacific"
        )


# Request Model
@dataclass
class SolarControlRequest:
    """Request data for solar blind control"""
    shade_state: Dict[str, int]  # Map of shade name to position (0=closed, 100=open)
    solar_reading: int  # Solar sensor reading (lux or similar)
    timestamp: datetime.datetime

    def validate(self) -> None:
        """Validate request data"""
        if not isinstance(self.shade_state, dict):
            raise InvalidSolarDataError("shade_state must be a dictionary")

        if not isinstance(self.solar_reading, (int, float)):
            raise InvalidSolarDataError("solar_reading must be numeric")

        if not isinstance(self.timestamp, datetime.datetime):
            raise InvalidSolarDataError("timestamp must be a datetime object")


# Result Model
@dataclass
class SolarControlResult:
    """Result of solar blind control operation"""
    status: str
    commands: List[str] = field(default_factory=list)
    sun_altitude: Optional[float] = None
    sun_azimuth: Optional[float] = None
    state_updates: Dict[str, Any] = field(default_factory=dict)
    message: Optional[str] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        result = {
            "status": self.status,
            "commands": self.commands
        }
        if self.message:
            result["message"] = self.message
        return result


# Controller
class SolarBlindController:
    """Controller for solar blind automation"""

    def __init__(self, config: SolarBlindConfig):
        """
        Initialize Solar Blind Controller

        Args:
            config: SolarBlindConfig instance with automation settings
        """
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate configuration parameters"""
        if not (-90 <= self.config.latitude <= 90):
            raise ConfigurationError("Latitude must be between -90 and 90")

        if not (-180 <= self.config.longitude <= 180):
            raise ConfigurationError("Longitude must be between -180 and 180")

        if self.config.solar_threshold <= 0:
            raise ConfigurationError("solar_threshold must be positive")

    def calculate_sun_position(self, timestamp: datetime.datetime) -> tuple[float, float]:
        """
        Calculate sun altitude and azimuth for given timestamp

        Args:
            timestamp: Datetime object (preferably with timezone)

        Returns:
            Tuple of (altitude, azimuth) in degrees
        """
        altitude = solar.get_altitude(
            self.config.latitude,
            self.config.longitude,
            timestamp
        )
        azimuth = solar.get_azimuth(
            self.config.latitude,
            self.config.longitude,
            timestamp
        )
        return altitude, azimuth

    def is_sun_in_watch_area(self, azimuth: float, altitude: float) -> bool:
        """
        Check if sun is within configured watch area

        Args:
            azimuth: Sun azimuth in degrees
            altitude: Sun altitude in degrees

        Returns:
            True if sun is in watch area
        """
        # Check azimuth bounds
        if not (self.config.start_azimuth < azimuth < self.config.end_azimuth):
            return False

        # Check altitude bounds based on azimuth position
        # Logic: use start_altitude for azimuth < 180, end_altitude for azimuth > 180
        if azimuth < 180:
            return altitude > self.config.start_altitude
        else:
            return altitude > self.config.end_altitude

    def _calculate_weighted_threshold(self, altitude: float) -> float:
        """
        Calculate altitude-weighted solar threshold

        Args:
            altitude: Current sun altitude in degrees

        Returns:
            Weighted solar threshold value
        """
        if altitude < self.config.lower_altitude:
            return self.config.solar_threshold * self.config.lower_altitude_percent
        elif altitude > self.config.upper_altitude:
            return self.config.solar_threshold * self.config.upper_altitude_percent
        else:
            # Linear interpolation between lower and upper altitude
            alt_weight = (
                (altitude - self.config.lower_altitude) /
                (self.config.upper_altitude - self.config.lower_altitude)
            )
            alt_weight_percent = (
                ((self.config.upper_altitude_percent - self.config.lower_altitude_percent) *
                 alt_weight) + self.config.lower_altitude_percent
            )
            return self.config.solar_threshold * alt_weight_percent

    def _determine_weather_condition(
        self,
        solar_reading: int,
        altitude: float
    ) -> str:
        """
        Determine weather condition based on solar reading

        Args:
            solar_reading: Solar sensor reading
            altitude: Current sun altitude

        Returns:
            Weather condition string ("Clear" or "Cloudy")
        """
        weighted_threshold = self._calculate_weighted_threshold(altitude)
        return "Clear" if solar_reading >= weighted_threshold else "Cloudy"

    def validate_shade_state(
        self,
        validate_command: str,
        shade_state: Dict[str, int]
    ) -> Optional[str]:
        """
        Validate that shades are in expected state, return retry command if not

        Args:
            validate_command: Either "confirmRaise" or "confirmClose"
            shade_state: Current shade positions

        Returns:
            Command to retry, or None if validation passed
        """
        validation_map = {
            'confirmRaise': {'target_state': 100, 'command': 'raiseAll'},
            'confirmClose': {'target_state': 0, 'command': 'closeAll'}
        }

        if validate_command not in validation_map:
            return None

        target = validation_map[validate_command]['target_state']

        # Check if any shade is not in target state
        for state in shade_state.values():
            if state != target:
                return validation_map[validate_command]['command']

        return None

    def determine_blind_command(
        self,
        request: SolarControlRequest,
        settings: Dict[str, Any]
    ) -> SolarControlResult:
        """
        Main controller method to determine blind commands

        Args:
            request: SolarControlRequest with current state
            settings: Dictionary of persisted settings from database

        Returns:
            SolarControlResult with commands and state updates
        """
        try:
            # Validate request
            request.validate()

            # Calculate sun position
            altitude, azimuth = self.calculate_sun_position(request.timestamp)

            # Determine weather condition
            condition = self._determine_weather_condition(request.solar_reading, altitude)

            # Determine if blinds should close based on condition
            blind_condition = "close" if condition in self.config.close_conditions else "open"

            # Check if sun is in watch area
            in_area = self.is_sun_in_watch_area(azimuth, altitude)

            # Initialize result
            result = SolarControlResult(
                status="success",
                sun_altitude=altitude,
                sun_azimuth=azimuth,
                diagnostics={
                    "weather_condition": condition,
                    "blind_condition": blind_condition,
                    "in_watch_area": in_area
                }
            )

            # State updates to persist
            result.state_updates['lastAlt'] = altitude
            result.state_updates['lastAzm'] = azimuth
            result.state_updates['lastCondition_logged'] = condition  # For logging weather

            # Handle shade state validation (retry logic)
            validate_setting = settings.get('validateShadeState', 'null')
            last_condition = settings.get('lastCondition', 'null')

            if validate_setting != 'null' and (blind_condition == last_condition or last_condition == 'null'):
                retry_command = self.validate_shade_state(validate_setting, request.shade_state)

                if retry_command is None:
                    # Validation passed, clear the validate flag
                    result.state_updates['validateShadeState'] = 'null'
                else:
                    # Validation failed, retry command
                    if not self.config.command_override:
                        result.commands.append(retry_command)

            # Main control logic (only if not overridden)
            if not self.config.command_override:
                if in_area:
                    # Check time buffer since last change
                    last_change_timestamp = settings.get('lastChangeDate', 0)
                    if isinstance(last_change_timestamp, str):
                        last_change_timestamp = float(last_change_timestamp) if last_change_timestamp != 'null' else 0

                    time_since_last_change = request.timestamp.timestamp() - last_change_timestamp

                    if time_since_last_change > self.config.change_buffer_duration_sec:
                        # Enough time has passed, check if condition changed
                        if blind_condition != last_condition:
                            if blind_condition == "close":
                                if last_condition != "close":
                                    result.commands.append('closeAll')
                                    result.state_updates['validateShadeState'] = 'confirmClose'
                            else:
                                if last_condition == "close":
                                    result.commands.append('raiseAll')
                                    result.state_updates['validateShadeState'] = 'confirmRaise'

                            # Update state
                            result.state_updates['lastCondition'] = blind_condition
                            result.state_updates['lastChangeDate'] = int(request.timestamp.timestamp())

                    result.state_updates['lastInArea'] = 'true'

                else:
                    # Sun not in area
                    # If last position was in area, raise blinds
                    if settings.get('lastInArea') == 'true':
                        if last_condition != "null":
                            result.commands.append('raiseAll')
                            result.state_updates['lastCondition'] = 'null'
                            result.state_updates['validateShadeState'] = 'confirmRaise'

                    result.state_updates['lastInArea'] = 'false'

            return result

        except InvalidSolarDataError as e:
            return SolarControlResult(
                status="Error",
                message=f"Invalid data: {e}"
            )

        except Exception as e:
            return SolarControlResult(
                status="Error",
                message=f"Unexpected error: {e}"
            )
