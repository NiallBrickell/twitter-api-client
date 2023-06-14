class TwitterAPIError(Exception):
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return f'TwitterAPIError: {self.text}'


class TwitterLoginError(Exception):
    pass
