import simplejson
from tornado.websocket import WebSocketHandler

from mage_ai.server.websockets.models import Client, Message
from mage_ai.server.websockets.utils import (
    filter_out_sensitive_data,
    parse_raw_message,
    should_filter_message,
    validate_message,
)
from mage_integrations.utils.parsers import encode_complex


class BaseHandler(WebSocketHandler):
    channel = None
    clients = set()
    running_executions_mapping = dict()

    def open(self, uuid: str):
        self.__class__.clients.add(self)
        self.uuid = uuid

    def on_close(self):
        self.__class__.clients.remove(self)

    def check_origin(self, origin):
        return True

    def on_message(self, raw_message: str):
        message = parse_raw_message(raw_message)
        message = validate_message(message)
        if message.error or message.executed:
            return self.send_message(message)

        client = Client.load(message=message)
        message = client.execute()
        if message.msg_id:
            self.__class__.running_executions_mapping[message.msg_id] = message

    @classmethod
    def send_message(self, message: Message) -> None:
        if isinstance(message, dict) and ('header' in message or 'parent_header' in message):
            message = Message.load_from_publisher_message(**message)

        if should_filter_message(message):
            return

        message = filter_out_sensitive_data(message)
        message = self.format_error(message)

        if message.msg_id in self.running_executions_mapping:
            message = self.running_executions_mapping.get(message.msg_id)

        for client in self.clients:
            client.write_message(simplejson.dumps(
                message.to_dict(),
                default=encode_complex,
                ignore_nan=True,
                use_decimal=True,
            ) if message else '')

    @classmethod
    def format_error(self, message: Message) -> Message:
        return message
