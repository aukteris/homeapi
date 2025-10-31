"""
Console Light Routes

Thin Flask route handler for console light functionality.
Delegates business logic to LGTVController.
"""

from flask import jsonify, Response
from classes.lg_tv_control import LGTVController, LGTVConfig


def console_light_route(token_file_path: str = "./secrets/lgtoken.json") -> Response:
    """
    Get color command based on current TV HDMI input

    Args:
        token_file_path: Path to LG TV authentication token file

    Returns:
        JSON response with status and color commands
    """
    # Create configuration with defaults
    config = LGTVConfig.default(token_file_path=token_file_path)

    # Create controller
    controller = LGTVController(config)

    # Get color command
    result = controller.get_color_command()

    # Return JSON response
    return jsonify(result.to_dict())


def register_console_light_routes(app, token_file_path: str = "./secrets/lgtoken.json"):
    """
    Register console light routes with Flask app

    Args:
        app: Flask application instance
        token_file_path: Path to LG TV authentication token file
    """
    @app.route('/console_light')
    def console_light():
        return console_light_route(token_file_path)
