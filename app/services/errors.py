class ProcessingError(Exception):
    def __init__(self, stage: str, message: str):
        self.stage = stage
        super().__init__(message)
