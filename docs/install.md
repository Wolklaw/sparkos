# Installing SparkOS next to Windows

SparkOS goes into empty space you make on one of your drives. Windows stays, with its files,
and you pick which one to start at power-on. Nothing in these steps erases a drive, as long as
you don't pick "Erase data and install" in step 4 of "Install".

What you need: a PC with an AMD or Intel graphics card (the image is the non-NVIDIA one), a
64-bit UEFI firmware, a USB stick of 16 GB or more (it gets erased), and at least 100 GB of free
space on a drive. 200 GB or more leaves room for games.

## Before (in Windows, about an hour)

1. **Back up what you can't lose** to somewhere that isn't this PC (an external drive or the
   cloud). Shrinking a drive is usually safe, but this is the one step where a mistake costs data.
2. **BitLocker / device encryption:** if Windows shows a BitLocker key for the drive you'll
   shrink (Settings > Privacy & security > Device encryption), write the recovery key down from
   account.microsoft.com/devices/recoverykey. Changing the boot menu can make Windows ask for it.
3. **Turn off Fast Startup:** Control Panel > Hardware and Sound > Power Options > "Choose what
   the power buttons do" > "Change settings that are currently unavailable" > untick "Turn on fast
   startup" > Save. With it on, Windows half-hibernates at shutdown, and SparkOS can only read your
   Windows drives, not write to them. (The firmware's own "Fast Boot" is a different setting;
   turn it off only if the boot menu key in step 1 of "Install" doesn't work.)
4. **Pick the drive** SparkOS goes on and **shrink it:** right-click Start > Disk Management >
   right-click the drive's volume > Shrink Volume. Type how much to free, in MB (204800 is 200 GB),
   and click Shrink. The freed space shows as black "Unallocated". Leave it empty: the installer
   uses it.
   - **Windows offers less than you asked for?** A file it can't move sits near the end of the
     drive. Windows names it: Event Viewer > Windows Logs > Application, the latest "Defrag" entry
     (event 259). If it's `$UsnJrnl` (the drive's change journal, which Windows recreates by
     itself), open Command Prompt as administrator and run `fsutil usn deletejournal /d E:` (your
     drive's letter), then try the shrink again. Game launchers' protected folders (the Xbox app's)
     are the other usual cause: uninstall those games first.

## Make the USB stick

1. Download every file of the release (the ISO comes in parts because GitHub limits each file to
   2 GB) into one folder.
2. On Windows, double-click **`join-iso.cmd`**; on Linux, run `sh join-iso.sh`. It joins the parts
   into `SparkOS-installer.iso` and checks it. It must say **OK**.
3. Write it to the stick with **Rufus** (choose **DD Image mode**; Rufus picks it by itself and says
   so) or **Fedora Media Writer** ("Select .iso file"). Windows may then offer to format the stick
   because it can't read Linux partitions: click Cancel.

## Install (about 20 minutes)

1. Shut down with the stick plugged in, turn on, and press your firmware's **boot menu key** while
   its logo shows (F8 on ASUS boards, F12 on many others, F11 on MSI). Pick the stick's **UEFI:**
   entry.
2. SparkOS starts from the stick and shows a "SparkOS installer" window: click **Install SparkOS**.
3. **Welcome:** your language. **Date and time:** your time zone.
4. **Installation method: the most important screen.**
   - Under **Destination**, click **Change destination** and tick **only** the drive you shrank.
     Leave every other drive, and the USB stick, unticked. Click **Select**.
   - Under **How would you like to install?** pick **Share disk with other operating systems**
     ("Keep current disk layout and use available space, to dual-boot"). Leave **Reclaim
     additional space** unticked.
   - **Never** pick **Erase data and install**: it removes every partition on the selected drive.
     If the installer says there isn't enough free space, stop and go back to Windows: the shrink
     didn't happen.
   - SparkOS makes its own small EFI partition and its system partitions in the free space. Your
     files and Windows aren't touched (checked byte for byte in a VM by every installer build).
5. **Storage configuration:** encryption is optional (you'd type its password at every start).
6. **Create Account:** your name, user name and password.
7. **Review and install:** check that the destination is the one drive you picked, then
   **Install**. When it's done, restart and take the stick out.
8. **Secure Boot** can stay on or off: SparkOS runs Fedora's kernel, signed by Fedora, so there's
   no key to enroll. With it on, the extra kernel modules SparkOS adds (Xbox wireless adapters,
   racing wheels, CPU power sensors) don't load yet, because they aren't signed; turn Secure Boot
   off in the firmware if you need those.

## First start

- The first start takes a little longer than the next ones. Then the sign-in screen, and **Spark Welcome**: your apps and game launchers, files from Windows
  (it reads the Windows drive and never writes to it), and a check of graphics, sound, printers
  and network.
- **Choosing Windows:** use your firmware's boot menu key and pick "Windows Boot Manager", or set
  the order in the firmware's Boot settings.
- Then [first-day.md](first-day.md), and [switching.md](switching.md) for what replaces which
  Windows app.

## If something goes wrong

- **The PC starts straight into Windows:** use the boot menu key and pick **SparkOS**, or move
  SparkOS first in the firmware's boot order.
- **"bad shim signature" at startup:** the Secure Boot key wasn't enrolled; see step 8 of "Install".
- **A bad update:** at startup, pick the previous version in SparkOS's boot menu. Updates never
  remove the version you had.
- **Windows asks for a BitLocker key:** type the recovery key from step 2 of "Before".
