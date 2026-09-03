from pydantic import Field
from pydantic_settings import BaseSettings

from .settings import BrowserSettings, RosettaSettings


class Settings(BaseSettings):
    # default_factory keeps .env reads out of import time: the first-run
    # setup must be able to create the file before settings are built.
    rosseta_settings: RosettaSettings = Field(default_factory=RosettaSettings)
    browser_settings: BrowserSettings = Field(default_factory=BrowserSettings)
