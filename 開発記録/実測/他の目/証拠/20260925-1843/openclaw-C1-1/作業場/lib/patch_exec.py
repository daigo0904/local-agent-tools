import sys; from unittest.mock import patch; from app import value; def mock_value(*args, **kwargs): return 2; patch('app.value', side_effect=mock_value).start()
