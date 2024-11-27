## DayZ Server Manager for Linux
Custom script for managing your DayZ Server on Linux <br/>
Currently being used without issue on `#1 [UK|PCGAMERS]`

### WARNING
Use this script at your own risk. I've modified to suit my specific needs. <br/>
You are free to copy or fork the script and edit to your liking.<br/>
Just please don't remove the credits at the top of the main script. Thank you.

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

## .workshop.cfg 
**Editing the `.workshop.cfg` file is real easy.**<br/>
- Add one workshop ID per line.<br/>
- The script will automatically check and append mod names each time you run: `./dayzserver.sh workshop`<br/>
- If a mod has been updated by the developer an optional notification can be sent to your Discord channel. <br/>
   - Just add your Discord URL in `.config.ini`

## Auto Restarts and Updates
The following cron jobs can be added to your DayZ Server users contab:<br/>
<br/>
```
@reboot /home/dayz/dayzserver.sh start > /dev/null 2>&1
*/1 * * * * /home/dayz/dayzserver.sh monitor > /dev/null 2>&1
*/30 * * * * /home/dayz/dayzserver backup > /dev/null 2>&1
```
- Line 1 simply starts the server when the Linux machine is rebooted or turned on.
- Line 2 checks to see if the server is crashed or has been shutdown remotely, then restarts it.
- Line 3 makes regular backups of your **storage** and **profile** folders.

You can use a service like CFTools to run server restarts (by remotely shutting it down).<br/>
CFTools shutdowns the server and `/home/dayz/dayzserver.sh monitor` will restart the server.<br/>

<br>

**MPORTANT NOTE** `monitor` will only restart the server if a remote shutdown (RCon) command was used.<br/>
`dayzserver.sh shutdown` done from the Linux command line will shutdown the server and prevent `monitor` from restarting it.
