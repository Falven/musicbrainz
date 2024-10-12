import argparse
import asyncio
import json
import logging
import os
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from PIL import Image
from prompt_toolkit import prompt
from rag_kit.logging import setup_logger
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential
from tqdm.asyncio import tqdm


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    reraise=True,
)
async def fetch_data(
    session: aiohttp.ClientSession,
    url: str,
    params: Dict[str, str] = None,
    logger: logging.Logger = None,
) -> Dict[str, Any]:
    async with session.get(url, params=params) as response:
        if response.status == 200:
            return await response.json()
        else:
            logger.warning(
                f"Failed to fetch data from {url}, status code: {response.status}"
            )
            return {}


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    reraise=True,
)
async def fetch_image_details(
    session: aiohttp.ClientSession,
    url: str,
    save_path: Optional[str],
    skip_existing: bool,
    logger: logging.Logger,
) -> Dict[str, Any]:
    local_path = None
    if save_path:
        local_path = os.path.join(save_path, os.path.basename(url))
        if skip_existing and os.path.exists(local_path):
            with Image.open(local_path) as image:
                width, height = image.size
                resolution = width * height
            return {
                "url": url,
                "dimensions": (width, height),
                "resolution": resolution,
                "local_path": local_path,
            }

    try:
        async with session.get(url) as response:
            image = Image.open(BytesIO(await response.read()))
            width, height = image.size  # returns (width, height)
            resolution = width * height
            if save_path and not (skip_existing and os.path.exists(local_path)):
                image.save(local_path)
            return {
                "url": url,
                "dimensions": (width, height),
                "resolution": resolution,
                "local_path": local_path,
            }
    except Exception as e:
        logger.error(f"Failed to fetch image details for URL {url}: {e}")
        return {}


async def fetch_release_groups(
    session: aiohttp.ClientSession,
    artist: str,
    album: str,
    offset: int,
    limit: int,
    logger: logging.Logger,
) -> Dict[str, Any]:
    params = {
        "query": f"artist:{artist} AND releasegroup:{album}",
        "fmt": "json",
        "limit": limit,
        "offset": offset,
    }
    try:
        return await fetch_data(
            session,
            "https://musicbrainz.org/ws/2/release-group/",
            params=params,
            logger=logger,
        )
    except RetryError as e:
        logger.error(f"Failed to fetch release groups after retries: {e}")
        return {}


async def get_release_groups(
    session: aiohttp.ClientSession,
    artist: str,
    album: str,
    logger: logging.Logger,
    progress_bar,
) -> List[Dict[str, Any]]:
    release_groups = []
    limit = 100

    initial_data = await fetch_release_groups(session, artist, album, 0, limit, logger)
    total_count = initial_data.get("count", 0)
    release_groups.extend(initial_data.get("release-groups", []))

    tasks = [
        fetch_release_groups(session, artist, album, offset, limit, logger)
        for offset in range(limit, total_count, limit)
    ]
    results = []

    progress_bar.total = total_count
    progress_bar.refresh()

    progress_bar.set_description(f"Fetching release groups for {artist} - {album}")
    for task in tqdm.as_completed(tasks):
        result = await task
        results.append(result)
        progress_bar.update(len(result.get("release-groups", [])))

    for result in results:
        release_groups.extend(result.get("release-groups", []))

    return release_groups


async def fetch_cover_art_urls(
    session: aiohttp.ClientSession, release_id: str, logger: logging.Logger
) -> Tuple[str, List[str]]:
    url = f"https://coverartarchive.org/release/{release_id}"
    try:
        data = await fetch_data(session, url, logger=logger)
        images = data.get("images", [])
        urls = [
            image["image"]
            for image in images
            if "image" in image and image.get("types") and "Front" in image["types"]
        ]
        return release_id, urls
    except RetryError:
        return release_id, []


async def get_cover_art_urls(
    session: aiohttp.ClientSession,
    release_ids: List[str],
    artist: str,
    album: str,
    logger: logging.Logger,
    progress_bar,
) -> List[Tuple[str, List[str]]]:
    tasks = [
        fetch_cover_art_urls(session, release_id, logger) for release_id in release_ids
    ]
    results = []

    progress_bar.total = len(tasks)
    progress_bar.set_description(f"Fetching cover art URLs for {artist} - {album}")
    for task in tqdm.as_completed(tasks):
        result = await task
        results.append(result)
        progress_bar.update(1)

    return results


async def find_image_details(
    session: aiohttp.ClientSession,
    urls: List[str],
    save_path: Optional[str],
    skip_existing: bool,
    desc: str,
    logger: logging.Logger,
    progress_bar,
) -> List[Dict[str, Any]]:
    tasks = [
        fetch_image_details(session, url, save_path, skip_existing, logger)
        for url in urls
    ]
    image_details = []

    progress_bar.total = len(tasks)
    progress_bar.set_description(desc)
    for task in tqdm.as_completed(tasks):
        result = await task
        image_details.append(result)
        progress_bar.update(1)

    valid_image_details = [detail for detail in image_details if detail]
    sorted_details = sorted(
        valid_image_details, key=lambda x: x["resolution"], reverse=True
    )
    return sorted_details


def save_output_to_file(data: Any, filepath: str, logger: logging.Logger) -> str:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as file:
        json.dump(data, file, indent=4)
    logger.info(f"Output saved to {filepath}")
    return filepath


async def process_artist_album(
    session: aiohttp.ClientSession,
    artist: str,
    album: str,
    release_type: Optional[str],
    status: Optional[str],
    save_images: bool,
    output_dir: str,
    skip_existing: bool,
    logger: logging.Logger,
    progress_bar,
) -> Dict[str, Any]:
    release_groups = await get_release_groups(
        session, artist, album, logger, progress_bar
    )
    if release_type:
        release_groups = [
            rg for rg in release_groups if rg.get("primary-type") == release_type
        ]
    if not release_groups:
        logger.error(
            f"No release group found for {artist} - {album} matching the criteria."
        )
        return {}

    release_ids = [
        release["id"]
        for release_group in release_groups
        for release in release_group.get("releases", [])
        if not status or release.get("status") == status
    ]

    cover_art_results = await get_cover_art_urls(
        session, release_ids, artist, album, logger, progress_bar
    )

    all_cover_art_urls = [url for _, urls in cover_art_results for url in urls]

    if not all_cover_art_urls:
        logger.error(f"No cover art found for {artist} - {album}.")
        return {}

    # Create directories for the artist and album
    artist_dir = os.path.join(output_dir, artist)
    album_dir = os.path.join(artist_dir, album)
    os.makedirs(album_dir, exist_ok=True)

    save_path = album_dir if save_images else None
    sorted_image_details = await find_image_details(
        session,
        all_cover_art_urls,
        save_path,
        skip_existing,
        desc=f"Downloading images for {artist} - {album}",
        logger=logger,
        progress_bar=progress_bar,
    )

    # Gather additional metadata
    metadata = {
        "artist": artist,
        "album": album,
        "release_type": release_type,
        "status": status,
        "cover_art_images": sorted_image_details,
    }
    save_output_to_file(metadata, os.path.join(album_dir, f"{album}.json"), logger)

    return sorted_image_details[0] if sorted_image_details else {}


async def main(
    config: Dict[str, Any], logger: logging.Logger, should_save_config: bool
) -> None:
    artists_albums = config["artists_albums"]
    release_type = config.get("release_type")
    status = config.get("status")
    save_images = config.get("save_images", False)
    output_dir = config.get("output_dir", ".")
    skip_existing = config.get("skip_existing", True)

    async with aiohttp.ClientSession() as session:
        highest_res_images = []
        tasks = []
        for artist_album in artists_albums:
            artist = artist_album["artist"]
            for album in artist_album["albums"]:
                progress_bar = tqdm(
                    total=1, desc=f"Processing {artist} - {album}", unit="task"
                )
                task = process_artist_album(
                    session,
                    artist,
                    album,
                    release_type,
                    status,
                    save_images,
                    output_dir,
                    skip_existing,
                    logger,
                    progress_bar,
                )
                tasks.append(task)

        results = await asyncio.gather(*tasks)

        for highest_res_image, artist_album in zip(results, artists_albums):
            artist = artist_album["artist"]
            for album in artist_album["albums"]:
                if highest_res_image:
                    highest_res_images.append(
                        {
                            "artist": artist,
                            "album": album,
                            "highest_resolution_image": highest_res_image,
                        }
                    )

        if highest_res_images:
            artist_dir = os.path.join(output_dir, artists_albums[0]["artist"])
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            final_filename = os.path.join(
                artist_dir, f"highest_resolution_images_{timestamp}.json"
            )
            save_output_to_file(highest_res_images, final_filename, logger)

        # Save config to a JSON file in the top-level directory if not loaded from a config file
        if should_save_config:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            config_filename = os.path.join(output_dir, f"config_{timestamp}.json")
            with open(config_filename, "w") as file:
                json.dump(config, file, indent=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch cover art for given artist and album names."
    )
    parser.add_argument(
        "--config_json",
        type=str,
        help="JSON string of configuration including artists, albums, release type, status, output directory, and save images flag",
    )
    parser.add_argument(
        "--config_file",
        type=str,
        help="Path to a JSON file containing the configuration",
    )
    parser.add_argument(
        "--verbosity",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="ERROR",
        help="Set the logging verbosity level",
    )
    args = parser.parse_args()

    log_level = getattr(logging, args.verbosity.upper(), logging.ERROR)
    logger = setup_logger(__name__, log_level)

    config_loaded_from_file = False

    if args.config_file:
        with open(args.config_file, "r") as file:
            config = json.load(file)
            config_loaded_from_file = True
    elif args.config_json:
        config = json.loads(args.config_json)
        config_loaded_from_file = True
    else:
        config = {}
        release_type = prompt(
            "Please enter the release type (e.g., Album, Single, or press Enter for all): "
        )
        config["release_type"] = release_type.strip() if release_type else None

        status = prompt(
            "Please enter the release status (e.g., Official, Promotion, or press Enter for all): "
        )
        config["status"] = status.strip() if status else None

        save_images_input = (
            prompt("Would you like to save the images? (yes/no) [no]: ", default="no")
            .strip()
            .lower()
        )
        config["save_images"] = save_images_input == "yes"

        output_dir = prompt(
            "Please enter the output directory (or press Enter for current directory): "
        ).strip()
        config["output_dir"] = output_dir if output_dir else "."

        skip_existing_input = (
            prompt(
                "Would you like to skip existing images? (yes/no) [yes]: ",
                default="yes",
            )
            .strip()
            .lower()
        )
        config["skip_existing"] = skip_existing_input != "no"

        artists_albums = []
        while True:
            artist = prompt("Please enter the artist name (or press Enter to finish): ")
            if not artist:
                break
            albums_input = prompt(
                "Please enter the album names (comma separated, or use quotes for names with commas): "
            )
            # Split albums by comma, respecting quoted commas
            albums = [
                album.strip().strip('"') for album in albums_input.split(",") if album
            ]
            artists_albums.append({"artist": artist, "albums": albums})

        config["artists_albums"] = artists_albums

    asyncio.run(main(config, logger, not config_loaded_from_file))
