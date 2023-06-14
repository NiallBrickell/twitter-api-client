# Adapted from twitter-redgalaxy-client
import dataclasses
import datetime
import pathlib
from types import NoneType
import typing

try:
    from mashumaro.mixins.orjson import DataClassORJSONMixin as MashuMaroORJSONMixin
except ImportError:
    MashuMaroORJSONMixin = object

# Adapted from  SNScrape
# (https://github.com/JustAnotherArchivist/snscrape/blob/master/snscrape/modules/twitter.py)


class BaseModel(MashuMaroORJSONMixin):
    def __getitem__(self, attr):
        return getattr(self, attr)

    def get(self, attr, default=None):
        if not hasattr(self, attr):
            return default
        return self[attr]
    
    def to_dict(self):
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Media(BaseModel):
    display_url: str
    expanded_url: str
    id: int
    media_url: str
    original_info: dict
    type: str
    features: dict

    @property
    def original_url(self):
        if self.type in ["photo", "gif"]:  # Unsure of gif.
            return f"{self.media_url}:orig"

    @property
    def large_url(self):
        if self.type in ["photo", "gif"]:  # Unsure of gif.
            return f"{self.media_url}:large"

    @property
    def medium_url(self):
        if self.type in ["photo", "gif"]:  # Unsure of gif.
            return f"{self.media_url}:medium"

    @property
    def small_url(self):
        if self.type in ["photo", "gif"]:  # Unsure of gif.
            return f"{self.media_url}:small"


@dataclasses.dataclass
class UploadMedia(BaseModel):
    path: pathlib.Path
    alt: typing.Optional[str] = None


@dataclasses.dataclass
class VideoVariant(BaseModel):
    bitrate: int
    content_type: str
    url: str


@dataclasses.dataclass
class VideoMeta(BaseModel):
    aspect: typing.List[int]
    duration: float
    variants: typing.List[VideoVariant]


@dataclasses.dataclass
class ExtendedMedia(Media):
    ext_media_availability: dict
    # Not available on newer twitter
    ext_media_color: typing.Optional[dict] = None
    data_info: typing.Optional[dict] = None
    # Video Only?
    additional_media_info: typing.Optional[dict] = None
    # features: typing.Optional[dict] = None

    @property
    def video_meta(self) -> typing.Optional[VideoMeta]:
        if self.data_info is not None and self.type == "video":
            meta = VideoMeta(
                self.data_info.get("aspect", [-1, -1]),
                self.data_info.get("duration_millis", 0) / 1000,
                [
                    VideoVariant(
                        variant.get("bitrate", -1),
                        variant.get("content_type", "video/unknown"),
                        variant.get("url", "https://video.twimg.com/"),
                    )
                    for variant in self.data_info.get("variants", [])
                ],
            )
            return meta
        else:
            return None


@dataclasses.dataclass
class TombTweet(BaseModel):
    id: int
    user: NoneType = None


@dataclasses.dataclass
class TweetMetrics(BaseModel):
    retweet_count: typing.Optional[int] = None
    like_count: typing.Optional[int] = None
    reply_count: typing.Optional[int] = None
    quote_count: typing.Optional[int] = None
    bookmark_count: typing.Optional[int] = None


@dataclasses.dataclass
class Tweet(BaseModel):
    id: int
    id_str: str
    created_at: datetime.datetime

    text: str
    links: typing.List[str]
    author: "User"
    public_metrics: TweetMetrics
    conversation_id: int
    language: str
    source: str  # May not exist anymore
    media: typing.Optional[typing.List["Media"]] = None
    extended_media: typing.Optional[typing.List["ExtendedMedia"]] = None
    retweeted_tweet: typing.Optional["Tweet"] = None
    quoted_tweet: typing.Optional["Tweet"] = None
    urls: typing.Optional[typing.List] = None


@dataclasses.dataclass
class UserMetrics(BaseModel):
    followers_count: typing.Optional[int] = None
    tweet_count: typing.Optional[int] = None
    listed_count: typing.Optional[int] = None
    like_count: typing.Optional[int] = None
    media_count: typing.Optional[int] = None
    friends_count: typing.Optional[int] = None


@dataclasses.dataclass
class User(BaseModel):
    username: str
    description: str
    id: int
    public_metrics: UserMetrics
    verified: bool
    is_blue_verified: bool
    can_dm: bool
    url: str
    name: typing.Optional[str] = None
    verified_type: typing.Optional[str] = None  # Includes Verified type
    created_at: typing.Optional[datetime.datetime] = None

    location: typing.Optional[str] = None
    protected: typing.Optional[bool] = False
    link_url: typing.Optional[str] = None
    profile_image_url: typing.Optional[str] = None
    profile_banner_url: typing.Optional[str] = None

    @classmethod
    def create_blank(cls, username, id):
        return cls(username, "", id, UserMetrics(), False)
