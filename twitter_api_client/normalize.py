# Adapted from twitter-redgalaxy-client
import re
import typing
from datetime import datetime, timezone

from .models import (
    TombTweet,
    User,
    Tweet,
    Media,
    UserMetrics,
    TweetMetrics,
    ExtendedMedia,
)
from .errors import TwitterAPIError


class UtilBox:
    @staticmethod
    def make_user(user_data: dict) -> User:
        if user_data['__typename'] != 'User':
            # Maybe rate limited or blocked from accessing this data. This type of error seems
            # to be transient and per-request rather than per-object
            raise TwitterAPIError(f"{user_data['__typename']} {user_data.get('reason')}")

        if 'legacy' in user_data:
            user_id = user_data['rest_id']
            user_data = {
                **user_data,
                **user_data['legacy'],
            }
            del user_data['legacy']
        else:
            user_id = user_data['id']

        username = user_data.get("screen_name")
        displayname = user_data.get("name")
        description = user_data.get("description")

        for url in user_data.get("entities", {}).get("description", {}).get("urls", []):
            description = description.replace(url.get("url"), url.get("expanded_url"))
        links = user_data.get("entities", {}).get("url", {}).get("urls", [])
        link_url = None
        if links:
            link_url = links[0].get("expanded_url")
            if link_url is None:
                # some links are short enough that they don't need expanding?
                link_url = links[0].get("url")

        metrics = UserMetrics(
            followers_count=user_data.get("followers_count", 0),
            tweet_count=user_data.get("statuses_count", 0),
            listed_count=user_data.get("listed_count", 0),
            like_count=user_data.get("favourites_count", 0),
            media_count=user_data.get("media_count", 0),
            friends_count=user_data.get("friends_count", 0),
        )
        profile_url = user_data.get("profile_image_url_https", None)
        if profile_url:
            profile_url = profile_url.replace("_normal", "_400x400")
        if isinstance(user_id, str):
            user_id = int(user_id)

        created_at = datetime.strptime(
            user_data["created_at"],
            "%a %b %d %H:%M:%S +0000 %Y",
        ).replace(tzinfo=timezone.utc).isoformat()

        return User(
            username=username,
            description=description,
            id=int(user_id),
            link_url=link_url,
            name=displayname,
            public_metrics=metrics,
            url=user_data.get('url', None),
            verified=user_data.get("verified", False),
            can_dm=user_data.get('can_dm', None),
            is_blue_verified=user_data.get('is_blue_verified', None),
            profile_banner_url=user_data.get("profile_banner_url", None),
            profile_image_url=profile_url,
            verified_type=None
            if not user_data["verified"]
            else user_data.get("verified_type", "Legacy"),
            created_at=created_at,
            location=user_data.get("location", None),
            protected=False,  # probably lol
            source="unofficial",
        )

    @staticmethod
    def common_tweet(
        true_tweet: dict, entry_globals: typing.Optional[dict],
    ):
        if true_tweet['__typename'] == 'TweetTombstone':
            # user doesn't exist anymore etc.
            return None
        if true_tweet.get('tweet'):
            true_tweet = true_tweet['tweet']
        if entry_globals:
            user_result = {}
            user_result["legacy"] = entry_globals["users"][str(true_tweet["user_id"])]
            user_result["legacy"]["id"] = str(true_tweet["user_id"])
            base_tweet = true_tweet
        else:
            user_result = true_tweet["core"]["user_results"]["result"]
            user_result["legacy"]["id"] = true_tweet["core"]["user_results"]["result"][
                "rest_id"
            ]
            # print("rest_id:", true_tweet["core"]["user_results"]["result"]["rest_id"])
            base_tweet = true_tweet["legacy"]
        if entry_globals:
            quoted_tweet = entry_globals["tweets"].get(
                str(base_tweet.get("quoted_status_id", "-1")), None
            )
            retweeted_tweet = entry_globals["tweets"].get(
                str(base_tweet.get("retweeted_status_id", "-1")), None
            )
        else:
            quoted_tweet = true_tweet.get("quoted_status_result", {}).get(
                "result", None
            ) or base_tweet.get("quoted_status_result", {}).get(
                "result", None
            ) 
            retweeted_tweet = true_tweet.get("retweeted_status_result", {}).get(
                "result", None
            ) or base_tweet.get("retweeted_status_result", {}).get(
                "result", None
            )

        if quoted_tweet:
            quoted_tweet = UtilBox.common_tweet(
                quoted_tweet, entry_globals,
            )
        if retweeted_tweet:
            retweeted_tweet = UtilBox.common_tweet(
                retweeted_tweet, entry_globals,
            )
        user = UtilBox.make_user(user_result)

        text = base_tweet.get("full_text", "")

        medias = base_tweet.get("extended_entities", {}).get("media", [])
        urls = base_tweet.get("entities", {}).get("urls", [])
        conversation_id = int(base_tweet.get("conversation_id_str", {}))
        reply_count = base_tweet.get("reply_count")
        retweet_count = base_tweet.get("retweet_count")
        like_count = base_tweet.get("favorite_count")
        quote_count = base_tweet.get("quote_count")
        bookmark_count = base_tweet.get("bookmark_count")
        view_count = true_tweet.get("views", {}).get("count", None)
        lang = base_tweet.get("lang")

        for link in urls:
            text = text.replace(link["url"], link["expanded_url"])

        spl_content: list[str] = text.split(" ")
        if spl_content[-1].startswith("https://t.co") and len(medias) > 0:
            spl_content.pop(-1)
        text = " ".join(spl_content)

        media_objs = {}
        for media in base_tweet.get("entities", {}).get("media", []):
            set_media = Media(
                display_url=media["display_url"],
                expanded_url=media["expanded_url"],
                features=media.get("features", {}),
                id=int(media["id_str"]),
                url=media["media_url_https"],
                type=media["type"],
                width=media['original_info']['width'],
                height=media['original_info']['height'],
                original_info=media["original_info"],
            )
            media_objs[set_media.id] = set_media

        for extended_media in medias:
            set_media = ExtendedMedia(
                display_url=extended_media["display_url"],
                expanded_url=extended_media["expanded_url"],
                ext_media_availability=extended_media["ext_media_availability"],
                ext_media_color=extended_media.get("ext_media_color"),
                features=extended_media.get("features", {}),
                id=int(extended_media["id_str"]),
                url=extended_media["media_url_https"],
                type=extended_media["type"],
                alt=extended_media.get('ext_alt_text'),
                width=media['original_info']['width'],
                height=media['original_info']['height'],
                original_info=extended_media["original_info"],
            )
            if set_media.type == "video":
                set_media.data_info = extended_media["video_info"]
                set_media.features = extended_media.get("features", None)
                set_media.preview_image_url = set_media.url
                set_media.expanded_url = extended_media["video_info"]['variants'][0]['url']
            # Animated gifs are just videos. (Thanks twitter)
            elif set_media.type == "animated_gif":
                set_media.data_info = extended_media["video_info"]
                set_media.features = extended_media.get("features", None)
                set_media.preview_image_url = set_media.url
                set_media.expanded_url = extended_media["video_info"]['variants'][0]['url']
            elif set_media.type != "photo":
                raise Exception(
                    f"Unknown type: {set_media.type}@{int(base_tweet['id_str'])}"
                )
            media_objs[set_media.id] = set_media

        media_objs = list(media_objs.values())

        source = base_tweet.get("source", "")
        if source:
            source = source.replace("\\/", "/")
            source = re.sub("<[^<]+?>", "", source)

        created_at = datetime.strptime(
            base_tweet["created_at"],
            "%a %b %d %H:%M:%S +0000 %Y",
        ).replace(tzinfo=timezone.utc).isoformat()

        metrics = TweetMetrics(
            retweet_count=retweet_count,
            like_count=like_count,
            reply_count=reply_count,
            quote_count=quote_count,
            bookmark_count=int(bookmark_count) if bookmark_count is not None else None,
            view_count=int(view_count) if view_count is not None else None,
        )
        quoted_status_id = base_tweet.get("quoted_status_id")
        retweeted_status_id = base_tweet.get("retweeted_status_id")
        return Tweet(
            id=int(base_tweet["id_str"]),
            id_str=base_tweet["id_str"],
            in_reply_to_status_id_str=base_tweet.get('in_reply_to_status_id_str'),
            in_reply_to_user_id_str=base_tweet.get('in_reply_to_user_id_str'),
            in_reply_to_status_id=int(base_tweet.get('in_reply_to_status_id_str')),
            quoted_status_id=int(quoted_status_id),
            retweeted_status_id=int(retweeted_status_id),
            created_at=created_at,
            text=text,
            urls=urls,
            author=user,
            public_metrics=metrics,
            conversation_id=conversation_id,
            language=lang,
            media=media_objs,
            retweeted_status=retweeted_tweet,
            quoted_status=quoted_tweet,
            source="unofficial",
        )

    @staticmethod
    def iter_timeline_data(
        timeline: dict, cursor: dict, global_objects: dict = {}, limit: int = None, run_count=0
    ):
        for i in timeline.get("instructions", []):
            entryType = list(i.keys())[0]
            if entryType == "type":
                if i[entryType] == "TimelineAddEntries":
                    for entry in UtilBox.iter_timeline_entry(i["entries"], global_objects):
                        if entry.get("type") == "cursor":
                            cursor[entry["direction"]] = entry
                        else:
                            yield entry['data']
                            run_count += 1
                            if limit is not None:
                                if limit > 0:
                                    limit -= 1
                                if limit == 0:
                                    break
                elif i[entryType] == "TimelineReplaceEntry":
                    for entry in UtilBox.iter_timeline_entry(
                        [i["entry"]], global_objects
                    ):
                        if entry.get("type") == "cursor":
                            cursor[entry["direction"]] = entry
            else:
                if entryType == "addEntries":
                    for entry in UtilBox.iter_timeline_entry(
                        i["addEntries"]["entries"], global_objects
                    ):
                        if entry.get("type") == "cursor":
                            cursor[entry["direction"]] = entry
                        else:
                            yield entry['data']
                            run_count += 1
                            if limit is not None:
                                if limit >= 0:
                                    limit -= 1
                                if limit == 0:
                                    break
                elif entryType == "replaceEntry":
                    for entry in UtilBox.iter_timeline_entry(
                        i["addEntries"]["entries"], global_objects
                    ):
                        if entry.get("type") == "cursor":
                            cursor[entry["direction"]] = entry

    @staticmethod
    def iter_timeline_entry(entries: list, entry_globals: dict):
        for entry in entries:
            entry_id = entry["entryId"]
            # print(entry_id)
            if entry_id.startswith("tweet-") or entry_id.startswith("sq-I-t-"):
                # print(entry)
                yield {
                    "type": "tweet",
                    "data": UtilBox.unpack_tweet(entry, entry_globals, entry_id),
                }
            elif entry_id.startswith("user-"):
                yield {
                    "type": "user",
                    'data': UtilBox.unpack_user(entry, entry_globals, entry_id),
                }
            elif entry_id.startswith("cursor") or entry_id.startswith("sq-C"):
                yield {
                    "type": "cursor",
                    **UtilBox.unpack_cursor(entry_id, entry["content"]),
                }

    @staticmethod
    def unpack_user(entryData: dict, entry_globals: dict, entry_id: str):
        if entryData.get("__typename") == "TimelineTimelineItem":
            user = (
                entryData.get("itemContent", {})
                .get("user_results", {})
                .get("result", {})
            )
            if not user:
                raise ValueError("User data missing? [Timeline V2]")
            user = UtilBox.make_user(user)
        elif entry_id.startswith("user-"):
            user_mini = entryData.get("content", {})
            if not user_mini:
                raise ValueError(
                    "User Pointer data missing? [Search Timeline]"
                )
            if user_mini.get("item", None) is not None:
                # TODO not checked
                user_mini = user_mini.get("item", None)
            elif "__typename" in user_mini:
                # V2 Search (GraphQL)
                user = (
                    user_mini.get("itemContent", {})
                    .get("user_results", {})
                    .get("result", {})
                )
                if not user:
                    raise ValueError("User data missing? [Timeline V2]")
                user = UtilBox.make_user(user)
                return user
            if user_mini is None:
                raise ValueError(
                    "Failed to retrieve user_mini [Search Timeline]"
                )
            user = entry_globals["users"][str(user_mini["content"]["user"]["id"])]
            # TODO: Need globals?
            user = UtilBox.make_user(user)
        else:
            raise ValueError(
                f"Unseen user type? [Unknown Timeline]: {entryData}"
            )

        return user

    @staticmethod
    def unpack_tweet(entryData: dict, entry_globals: dict, entry_id: str):
        if entryData.get("__typename") == "TimelineTimelineItem":
            tweet = (
                entryData.get("itemContent", {})
                .get("tweet_results", {})
                .get("result", {})
            )
            if not tweet:
                raise ValueError("Tweet data missing? [Timeline V2]")
            tweet = UtilBox.common_tweet(tweet, None)
        elif entry_id.startswith("sq-I-t-") or entry_id.startswith("tweet-"):
            tweet_mini = entryData.get("content", {})
            if not tweet_mini:
                raise ValueError(
                    "Tweet Pointer data missing? [Search Timeline]"
                )
            if tweet_mini.get("item", None) is not None:
                tweet_mini = tweet_mini.get("item", None)
            elif "__typename" in tweet_mini:
                # V2 Search (GraphQL)
                tweet = (
                    tweet_mini.get("itemContent", {})
                    .get("tweet_results", {})
                    .get("result", {})
                )
                if not tweet:
                    tomb_id = int(entry_id.split("-")[-1])
                    if tomb_id:
                        tweet = TombTweet(id=tomb_id)
                        return tweet
                    print(entryData)
                    raise ValueError("Tweet data missing? [Timeline V2]")
                tweet = UtilBox.common_tweet(tweet, None)
                return tweet
            if tweet_mini is None:
                raise ValueError(
                    "Failed to retrieve tweet_mini [Search Timeline]"
                )
            tweet = entry_globals["tweets"][str(tweet_mini["content"]["tweet"]["id"])]
            tweet = UtilBox.common_tweet(tweet, entry_globals)
        else:
            raise ValueError(
                f"Unseen Tweet type? [Unknown Timeline]: {entryData}"
            )

        return tweet

    @staticmethod
    def unpack_cursor(entry_id, cursor: dict):

        content = cursor.get("content", {})
        operation = cursor.get("operation", {})
        v2 = True if cursor.get("__typename") else False

        if not content and not operation and not v2:
            # self.logging.debug(cursor)
            raise Exception("Cursor Content missing?")
        else:
            # self.logging.debug(entry_id, cursor)
            if entry_id.startswith("sq-C"):
                content = operation["cursor"]
                return {
                    "direction": content.get("cursorType").lower(),
                    "value": content.get("value"),
                }
            elif entry_id.startswith("cursor-"):
                if operation.get("cursor"):
                    content = operation["cursor"]
                else:
                    # probably v2
                    content = cursor
                return {
                    "direction": content.get("cursorType", "").lower(),
                    "value": content.get("value"),
                }
            else:
                return {
                    "direction": content.get("cursorType", "").lower(),
                    "value": content.get("value"),
                }

def get_instructions(inner_data: dict):
    if inner_data.get('user'):
        result = inner_data['user']['result']
        if result.get('timeline_v2'):
            return result['timeline_v2']['timeline']
        elif result.get('timeline'):
            return result['timeline']['timeline']
        else:
            # typename contains error
            raise TwitterAPIError(f"{result['__typename']}{' '+result['reason'] if result.get('reason') else ''}")
    if inner_data.get('threaded_conversation_with_injections_v2'):
        return inner_data['threaded_conversation_with_injections_v2']


def normalize_resp(data: dict):
    inner_data: dict = data.get("data", {})
    
    instructions = get_instructions(inner_data)
    if instructions is None:
        # likely an 'errors' field in data that will be handled
        instructions = {}
    cursor = {}
    
    res = list(UtilBox.iter_timeline_data(instructions, cursor))
    return [r for r in res if r]
