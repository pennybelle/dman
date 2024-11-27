## DayZ Server Manager for Linux
Custom Script for Managing the PCGamers.win DayZ Server

### WARNING
Use this script at your own risk. I've modified to suit my specific needs. <br/>
You are free to copy or fork the script and edit to your liking. 

### Basic Usage
- Download [dayzserver.sh](https://raw.githubusercontent.com/haywardgg/DayZ_Server_Manager/5536718fb3361cf4f3baad9293f61918636e16c7/dayzserver.sh) to the root of your DayZ server home drive.
- Edit the script and change the config settings. i.e Username, etc.
- Then type: `chmod +x dayzserver.sh` <br/>
You will get instructions on how to start stop etc after first run.

## First RUN
1. Run the script `./dayzserver.sh`
2. Wait until it has finished, then follow the instructions.
3. Edit the `.config.ini` file with your preferences.
4. Add your Mod ID's to the `.workshop.cfg` file.
   - Don't worry about adding the mod name. The script will do that later.
   - One ModID per line only.
5. Edit the `serverfiles/battleye/beserver_x64_active_*.cfg`
   - Change the RCon password and port number, or leave as default.
   - Make sure the RCon and the Game Server ports aren't the same.
6. In your `serverfiles/serverDZ.cfg` file change your hostname and other settings.
   - Make sure there is a **steamQueryPort** setting. i.e `steamQueryPort = 27016;`
7. Run the script again and your server will be online within minutes.

