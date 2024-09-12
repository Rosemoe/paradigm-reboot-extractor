# Paradigm: Reboot Extractor
Extract metadata and resources from Paradigm: Reboot game APK, including:
- Song Metadata
- Song resources
  - Cover image
  - Song audio (preview+full)
  - Charts
- Skin resources (Sprite and Texture2D only)
## Usage
This tool is tested on Windows and Python 3.10.   
Install required packages via command: `pip install UnityPy,fsb5`
### Command-line Usage
```
Usage: extractor.py -i <apk_path> [-a <assets_apk_path>] [-h] [--songs] [--skins]
Options:
-i <apk_path>           Specify the input (base) apk file path
-a <assets_apk_path>    Specify additional assets apk file path
--songs                 Export song resources
--skins                 Export skin resources
-h                      Show this help
```
By default, only song metadata is exported.
### Example
Export song metadata and all resources, supposing you've downloaded split apks from Google Play.
```
python extractor.py -i .\base.apk -a .\split_UnityDataAssetPack.apk --songs --skins
```
# Related Enum Types
All enum type values used in song metadata can be found [here](./EnumTypes.md)
