# Cover Art Hunter

## Description

Cover Art Hunter is a CLI tool designed to fetch cover art for specified artists and albums from MusicBrainz and save the results as JSON files. Optionally, it can also download and save the cover art images in a structured directory hierarchy.

## Features

- Fetch cover art for given artists and albums.
- Save cover art metadata as JSON files.
- Optionally download and save cover art images.
- Create a structured directory hierarchy for organizing the output.

## Arguments and Flags

- `--config_json` (optional): A JSON string containing the configuration including artists, albums, release type, status, output directory, and save images flag.
  - Example: 
\```json
{
    "artists_albums": [
        {
            "artist": "Pink Floyd",
            "albums": ["The Dark Side of the Moon"]
        },
        {
            "artist": "Led Zeppelin",
            "albums": ["IV"]
        }
    ],
    "release_type": "Album",
    "status": "Official",
    "save_images": true,
    "output_dir": "/path/to/output",
    "skip_existing": true
}
\```

- `--config_file` (optional): Path to a JSON file containing the configuration.
  - Example: `--config_file /path/to/config.json`

- `--verbosity` (optional): Set the logging verbosity level. Choices are `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Default is `INFO`.
  - Example: `--verbosity DEBUG`

## Usage

### Command Line Usage

#### With Image Saving

```sh
python cover_art_hunter.py --artist_album_json '[{"artist": "Pink Floyd", "albums": ["The Dark Side of the Moon", "Wish You Were Here"]}, {"artist": "Led Zeppelin", "albums": ["IV", "Physical Graffiti"]}]' --release_type Album --status Official --save_images
```

#### Without Image Saving

```sh
python cover_art_hunter.py --artist_album_json '[{"artist": "Pink Floyd", "albums": ["The Dark Side of the Moon", "Wish You Were Here"]}, {"artist": "Led Zeppelin", "albums": ["IV", "Physical Graffiti"]}]' --release_type Album --status Official
```

### Interactive Usage

```sh
python cover_art_hunter.py
```

Follow the prompts

```sh
Please enter the release type (e.g., Album, Single, or press Enter for all): Album
Please enter the release status (e.g., Official, Promotion, or press Enter for all): Official
Would you like to save the images? (yes/no) [no]: 
Please enter the output directory (or press Enter for current directory): /path/to/output
Would you like to skip existing images? (yes/no) [yes]: 
Please enter the artist name (or press Enter to finish): Pink Floyd
Please enter the album names (comma separated, or use quotes for names with commas): "The Dark Side of the Moon", "Wish You Were Here"
Please enter the artist name (or press Enter to finish): Led Zeppelin
Please enter the album names (comma separated, or use quotes for names with commas): IV, "Physical Graffiti"
Please enter the artist name (or press Enter to finish): 
```

### Output

The tool will save the configuration used in the top-level output directory as a JSON file named `config_<timestamp>.json`.

.
├── Pink Floyd
│   ├── The Dark Side of the Moon
│   │   ├── The_Dark_Side_of_the_Moon.json
│   │   ├── cover_art_image1.jpg
│   │   ├── cover_art_image2.jpg
│   │   └── ...
│   ├── Wish You Were Here
│   │   ├── Wish_You_Were_Here.json
│   │   ├── cover_art_image1.jpg
│   │   ├── cover_art_image2.jpg
│   │   └── ...
│   └── highest_resolution_images_20240702_123456.json
├── Led Zeppelin
│   ├── IV
│   │   ├── IV.json
│   │   ├── cover_art_image1.jpg
│   │   ├── cover_art_image2.jpg
│   │   └── ...
│   ├── Physical Graffiti
│   │   ├── Physical_Graffiti.json
│   │   ├── cover_art_image1.jpg
│   │   ├── cover_art_image2.jpg
│   │   └── ...
│   └── highest_resolution_images_20240702_123456.json

- Each artist has a directory.
- Each album by an artist has its own directory within the artist's directory.
- Album-specific JSON files and images (if downloaded) are saved within the respective album directories.
- A JSON file containing the highest resolution images for each artist is saved within the artist's directory.

#### Sample JSON Output

```json
{
    "artist": "Pink Floyd",
    "album": "The Dark Side of the Moon",
    "release_type": "Album",
    "status": "Official",
    "cover_art_images": [
        {
            "url": "http://coverartarchive.org/release/12345/cover.jpg",
            "dimensions": [1600, 1600],
            "resolution": 2560000,
            "local_path": "Pink Floyd/The Dark Side of the Moon/cover.jpg"
        },
        ...
    ]
}
```

This JSON file contains metadata about the cover art images, including their URLs, dimensions, resolution, and local paths (if images were downloaded).

## Notes

Ensure you have the required Python packages installed. It's recommended to use `poetry` for managing dependencies:

1. Install `poetry` if you haven't already:
   ```sh
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. Install the dependencies using `poetry`:
   ```sh
   poetry install
   ```

The required packages are:

    - aiohttp
    - PIL (Pillow)
    - tenacity
    - prompt_toolkit (for enhanced input handling)
