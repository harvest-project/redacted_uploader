import html

from plugins.redacted.utils import get_shorter_joined_artists
from upload_studio.upload_metadata import MusicMetadata
from upload_studio.utils import strip_invalid_path_characters

ENCODING_NAME_MAP = {
    MusicMetadata.ENCODING_192: '192',
    MusicMetadata.ENCODING_APS: 'APS',
    MusicMetadata.ENCODING_V2: 'V2',
    MusicMetadata.ENCODING_V1: 'V1',
    MusicMetadata.ENCODING_256: '256',
    MusicMetadata.ENCODING_APX: 'APX',
    MusicMetadata.ENCODING_V0: 'V0',
    MusicMetadata.ENCODING_320: '320',
    MusicMetadata.ENCODING_LOSSLESS: 'Lossless',
    MusicMetadata.ENCODING_24BIT_LOSSLESS: 'Lossless 24bit',
    MusicMetadata.ENCODING_OTHER: 'Other',
}


def get_torrent_name_for_upload(music_metadata):
    red_group = music_metadata.additional_data['source_red_group']
    music_info = red_group['musicInfo']
    artists = get_shorter_joined_artists(music_info, red_group['name'])
    name = html.unescape(red_group['name'])
    if len(name) > 70:
        name = name[:67] + '...'
    media = music_metadata.media
    year = music_metadata.edition_year
    return strip_invalid_path_characters('{artists} - {name} - {year} ({media} - {format} - {encoding})'.format(
        artists=artists,
        name=name,
        year=year,
        media=media,
        format=music_metadata.format,
        encoding=ENCODING_NAME_MAP[music_metadata.encoding],
    ))
