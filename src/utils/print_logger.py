class PrintLogger(object):
    def __init__(self, logger, stdout):
        self.logger = logger
        self.stdout = stdout

    def write(self, message):
        # Avoid writing empty messages or newlines
        if message.rstrip() != "":
            self.logger.info(message.rstrip())
        # Also write the message to stdout
        self.stdout.write(message)

    def flush(self):
        # This flush method is needed for python 3 compatibility.
        # It will flush the actual stdout object.
        self.stdout.flush()