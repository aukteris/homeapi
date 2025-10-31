"""
Solar Blind Routes

Thin Flask route handler for solar blind control functionality.
Delegates business logic to SolarBlindController.
"""

import json
import datetime
import pytz
from flask import request, jsonify, Response
from classes.solar_blind_control import (
    SolarBlindController,
    SolarBlindConfig,
    SolarControlRequest
)


def solar_blind_route(db_session) -> Response:
    """
    Control automated blinds based on sun position and weather

    Args:
        db_session: Database session for settings and logging

    Returns:
        JSON response with status and blind commands
    """
    # Load settings from database
    settings = db_session.getSettings()

    # Parse request parameters
    try:
        shade_state = json.loads(request.args.get('shade_state'))
        solar_reading = int(request.args.get('solar'))
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        return jsonify({
            "status": "Error",
            "message": f"Invalid request parameters: {e}"
        })

    # Get current timestamp
    now = datetime.datetime.now(tz=pytz.timezone('US/Pacific'))

    # Create configuration from database settings
    config = SolarBlindConfig(
        latitude=45.46692,  # TODO: make configurable via database
        longitude=-122.79286,  # TODO: make configurable via database
        timezone_name="US/Pacific",
        start_azimuth=settings.get('startAzm', 0),
        end_azimuth=settings.get('endAzm', 360),
        start_altitude=settings.get('startAlt', 0),
        end_altitude=settings.get('endAlt', 90),
        solar_threshold=settings.get('solarThresh', 100),
        lower_altitude=settings.get('lowerAlt', 20),
        upper_altitude=settings.get('upperAlt', 60),
        lower_altitude_percent=settings.get('lowerAltPer', 0.5),
        upper_altitude_percent=settings.get('upperAltPer', 1.0),
        change_buffer_duration_sec=settings.get('changeBufferDurationSec', 1800),
        command_override=settings.get('commandOverride', 0) == 1,
        close_conditions=["Cloudy"]  # Could be made configurable
    )

    # Create request object
    control_request = SolarControlRequest(
        shade_state=shade_state,
        solar_reading=solar_reading,
        timestamp=now
    )

    # Create controller and execute
    controller = SolarBlindController(config)
    result = controller.determine_blind_command(control_request, settings)

    # Persist state updates to database
    for key, value in result.state_updates.items():
        if key == 'lastCondition_logged':
            # Special case: log weather condition to history
            db_session.logCondition(value)
        else:
            # Regular setting update
            db_session.updateSetting(value, key)

    # Debug output (matches original behavior)
    print(result.to_dict())

    # Return JSON response
    return jsonify(result.to_dict())


def register_solar_blind_routes(app, db_session):
    """
    Register solar blind routes with Flask app

    Args:
        app: Flask application instance
        db_session: Database session for settings and logging
    """
    @app.route('/sun_control', methods=['GET'])
    def sun_control():
        if request.method == 'GET':
            return solar_blind_route(db_session)
        else:
            return ('', 204)
