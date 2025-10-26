import logging
import os
import requests
from typing import Union

from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response
from ask_sdk_model.ui import StandardCard
from ask_sdk_model.interfaces.audioplayer import (
    PlayDirective, PlayBehavior, AudioItem, Stream, AudioItemMetadata,
    StopDirective)
from ask_sdk_model.interfaces import display

from .track import Track
from .subsonic_api import SubsonicConnection
from .media_queue import MediaQueue

logger = logging.getLogger(__name__)

#
# Functions
#


def start_playback(mode: str, text: str, card_data: dict, track_details: Track, handler_input: HandlerInput) -> Response:
    """Function to play audio.

    Begin playing audio when:

        - Play Audio Intent is invoked.
        - Resuming audio when stopped / paused.
        - Next / Previous commands issues.

    .. note ::
       - https://developer.amazon.com/docs/custom-skills/audioplayer-interface-reference.html#play
           - REPLACE_ALL: Immediately begin playback of the specified stream,
             and replace current and enqueued streams.

    :param str mode: play | continue - Play immediately or enqueue a track
    :param str text: Text which should be spoken before playback starts
    :param dict card_data: Data to display on a card
    :param Track track_details: A Track object containing details of the track to use
    :param HandlerInput handler_input: The Amazon Alexa HandlerInput object
    :return: Amazon Alexa Response class
    :rtype: Response
    """
    
    metadata = add_screen_background(track_details)
    
    if mode == 'play':
        # Starting playback
        logger.debug('In start_playback() - play mode')

        if card_data:
            # Cards are only supported if we are starting a new session
            handler_input.response_builder.set_card(
                StandardCard(
                    title=card_data['title'], text=card_data['text'],
                    # image=Image(
                    #    small_image_url=card_data['small_image_url'],
                    #    large_image_url=card_data['large_image_url'])
                )
            )

        handler_input.response_builder.add_directive(
            PlayDirective(
                play_behavior=PlayBehavior.REPLACE_ALL,
                audio_item=AudioItem(
                    stream=Stream(
                        token=track_details.id,
                        url=track_details.uri,
                        offset_in_milliseconds=track_details.offset,
                        expected_previous_token=None),
                    metadata=metadata
                )
            )
        ).set_should_end_session(True)

        if text:
            # Text is not supported if we are continuing an existing play list
            handler_input.response_builder.speak(text)

        logger.debug(f'Track ID: {track_details.id}')
        logger.debug(f'Track Previous ID: {track_details.previous_id}')
        logger.info(f'Playing track: {track_details.title} by: {track_details.artist}')

    elif mode == 'continue':
        # Continuing Playback
        logger.debug('In start_playback() - continue mode')

        handler_input.response_builder.add_directive(
            PlayDirective(
                play_behavior=PlayBehavior.ENQUEUE,
                audio_item=AudioItem(
                    stream=Stream(
                        token=track_details.id,
                        url=track_details.uri,
                        # Offset is 0 to allow playing of the next track from the beginning
                        # if the Previous intent is used
                        offset_in_milliseconds=0,
                        expected_previous_token=track_details.previous_id),
                    metadata=metadata
                )
            )
        ).set_should_end_session(True)

        logger.debug(f'Track ID: {track_details.id}')
        logger.debug(f'Track Previous ID: {track_details.previous_id}')
        logger.info(f'Enqueuing track: {track_details.title} by: {track_details.artist}')

    return handler_input.response_builder.response


def stop(handler_input: HandlerInput) -> Response:
    """Stop playback

    :param HandlerInput handler_input: The Amazon Alexa HandlerInput object
    :return: Amazon Alexa Response class
    :rtype: Response
    """
    logger.debug('In stop()')

    handler_input.response_builder.add_directive(StopDirective())

    return handler_input.response_builder.response

def get_brainz_album_art(artist, album):
        def fetch_cover_art_brainz(release_id):
            # Cover Art Archive API endpoint
            art_url = f"https://coverartarchive.org/release/{release_id}/"
            try:
                response = requests.get(art_url, timeout=3)
                response.raise_for_status()
            
                data = response.json()
                images = data.get('images', [])
                if images:
                    return images[0]['thumbnails']  # Return the first available cover art
            except requests.exceptions.RequestException as e:
                print(f"An error occurred while fetching cover art: {e}")

            return None
        
        brainz_url = "https://musicbrainz.org/ws/2/release/"
        query = f"{brainz_url}?query=artist:{artist}+AND+release:{album}&fmt=json"
        try: 
            response = requests.get(query, timeout=3)
            response.raise_for_status()
            
            data = response.json()
            release_list = data.get('releases', [])
            
            if release_list:
                release_id = release_list[0]['id']
                cover_art = fetch_cover_art(release_id)
                return cover_art
        except requests.exceptions.Timeout:
            print("The request timed out. Please try again.")
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")

        return None
        
def get_lastfm_album_art(artist_name, album_name, api_key):
        url = "http://ws.audioscrobbler.com/2.0/"
        # Parameters for the API request
        params = {
            'method': 'album.getinfo',
            'api_key': api_key,
            'artist': artist_name,
            'album': album_name,
            'format': 'json'
        }

        try:
            response = requests.get(url, params=params, timeout=2)
            response.raise_for_status()  # Raise an error for bad responses

            data = response.json()
            if 'album' in data:
                # Get the cover art URL
                cover_art_url = data['album']['image'][-1]['#text']  # Get the largest image
                return cover_art_url

        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
        
        return None

def add_screen_background(track_details: Track) -> Union[AudioItemMetadata, None]:
    """Add background to card.

    Cards are viewable on devices with screens and in the Alexa
    app.

    :param dict card_data: Dictionary containing card data
    :return: An Amazon AudioItemMetadata object or None if card data is not present
    :rtype: AudioItemMetadata | None
    """
    logger.debug('In add_screen_background()')

    if track_details:
        # there are 2 ways to get cover art, musicBrainz or lastfm API
    
        api_key = os.getenv('LASTFM_APIKEY')

        cover_art_url = get_lastfm_album_art(track_details.artist, track_details.album, api_key) if api_key else None
        #cover_art_list = get_brainz_album_art(track_details.artist, track_details.album)


        metadata = AudioItemMetadata(
            title=track_details.title,
            subtitle=track_details.artist,
            art=display.Image(
                    content_description=track_details.album,
                    sources=[
                        display.ImageInstance(
                            url= cover_art_url or 'https://github.com/navidrome/navidrome/raw/master/resources/logo-192x192.png'
                        )
                    ]
                ),
            background_image=display.Image(
                    content_description=track_details.title,
                    sources=[
                        display.ImageInstance(
                            url= cover_art_url or 'https://github.com/navidrome/navidrome/raw/master/resources/logo-192x192.png'
                        )
                    ]
                )
        )

        return metadata
    else:
        return None


def enqueue_songs(api: SubsonicConnection, queue: MediaQueue, song_id_list: list) -> None:
    """Enqueue songs

    Add Track objects to the queue deque

    :param SubsonicConnection api: A SubsonicConnection object to allow access to the Navidrome API
    :param MediaQueue queue: A MediaQueue object
    :param list song_id_list: A list of song IDs to enqueue
    :return: None
    """

    for song_id in song_id_list:
        song_details = api.get_song_details(song_id)
        song_uri = api.get_song_uri(song_id)

        # Create track object from song details
        new_track = Track(song_details.get('song').get('id'),
                          song_details.get('song').get('title'),
                          song_details.get('song').get('artist'),
                          song_details.get('song').get('artistId'),
                          song_details.get('song').get('album'),
                          song_details.get('song').get('albumId'),
                          song_details.get('song').get('track'),
                          song_details.get('song').get('year'),
                          song_details.get('song').get('genre'),
                          song_details.get('song').get('duration'),
                          song_details.get('song').get('bitRate'),
                          song_uri,
                          0,
                          None)

        # Add track object to queue
        queue.add_track(new_track)
