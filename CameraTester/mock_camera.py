"""
Mock Camera - Legacy compatibility wrapper
Redirects to MockGigECamera for GigE Vision emulation
"""
from mock_gige_camera import MockGigECamera, create_mock_cameras

__all__ = ['MockGigECamera', 'create_mock_cameras']
