import io
import logging
import sys
import types
import unittest
from contextlib import redirect_stderr
from unittest import mock


def _install_fake_dingtalk_stream():
    module = types.ModuleType("dingtalk_stream")
    utils_module = types.ModuleType("dingtalk_stream.utils")
    utils_module.DINGTALK_OPENAPI_ENDPOINT = "https://oapi.dingtalk.com"

    class ChatbotHandler:
        pass

    class CallbackMessage:
        pass

    class AckMessage:
        STATUS_OK = "OK"

    class ChatbotMessage:
        @staticmethod
        def from_dict(data):
            return data

    class Credential:
        pass

    class DingTalkStreamClient:
        pass

    module.ChatbotHandler = ChatbotHandler
    module.CallbackMessage = CallbackMessage
    module.AckMessage = AckMessage
    module.ChatbotMessage = ChatbotMessage
    module.Credential = Credential
    module.DingTalkStreamClient = DingTalkStreamClient
    module.utils = utils_module
    return module


def _install_fake_dotenv():
    module = types.ModuleType("dotenv")
    module.load_dotenv = lambda *args, **kwargs: None
    return module


class DingTalkStreamLoggingTests(unittest.TestCase):
    def test_logging_guard_handles_sdk_exception_call_with_extra_arg(self):
        fake_stream = _install_fake_dingtalk_stream()
        fake_dotenv = _install_fake_dotenv()
        with mock.patch.dict(
            sys.modules,
            {
                "dingtalk_stream": fake_stream,
                "dingtalk_stream.utils": fake_stream.utils,
                "dotenv": fake_dotenv,
            },
        ):
            if "main" in sys.modules:
                del sys.modules["main"]
            import main

        main._install_dingtalk_stream_logging_guard()

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("dingtalk_stream.stream")
        previous_handlers = logger.handlers[:]
        previous_propagate = logger.propagate
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.ERROR)

        stderr = io.StringIO()
        try:
            try:
                raise TimeoutError("timed out during opening handshake")
            except TimeoutError as exc:
                with redirect_stderr(stderr):
                    logger.exception("unknown exception", exc)
        finally:
            logger.handlers = previous_handlers
            logger.propagate = previous_propagate

        self.assertNotIn("--- Logging error ---", stderr.getvalue())
        self.assertIn("unknown exception: timed out during opening handshake", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
