"""
Backward compatibility entry point for app-use CLI.

This file has been refactored. The new CLI is in the app_use.cli module.
"""

import sys
import warnings

# Show deprecation warning
warnings.warn(
	'Direct import of app_use.cli is deprecated. '
	'The CLI has been refactored into app_use.cli module. '
	'This compatibility layer will be removed in a future version.',
	DeprecationWarning,
	stacklevel=2,
)

# Import the new CLI main function
try:
	from app_use.cli.cli import main
except ImportError:
	print('⚠️ CLI module is not available. Please reinstall app-use.')
	sys.exit(1)


# For backward compatibility, expose the main function
if __name__ == '__main__':
	main()
