# Installing SparkOS on this PC (next to Windows)

For this PC: SparkOS goes into space freed on **E:** (the 1 TB "Games" NVMe). **C:** (Windows) and
**D:** ("Scrap", downloads and temp) are not touched. Windows stays and is picked from a boot menu.

Not tested on real hardware yet: this is the first install. Every build boots in a VM in CI, but
the installer, dual boot and your devices are checked for the first time here (Phase 5 in
[PLAN.md](../PLAN.md)).

## Before (in Windows, about an hour)

1. **Back up `E:\Personal Projects`** to somewhere that isn't this PC (an external drive or cloud).
   Shrinking a drive is usually safe, but this is the one step where a mistake costs data.
2. **BitLocker / device encryption:** if Windows shows a BitLocker key for C: or E:
   (Settings > Privacy & security > Device encryption), write the recovery key down from
   account.microsoft.com/devices/recoverykey. Changing the boot menu can make Windows ask for it.
3. **Turn off Fast Startup:** Control Panel > Power Options > "Choose what the power buttons do" >
   "Change settings that are currently unavailable" > untick "Turn on fast startup". With it on,
   Windows half-hibernates and SparkOS can only read your Windows drives, not write.
4. **Uninstall the games on E:** through Steam, Epic, Battle.net and the Xbox app (the Xbox app's
   protected folders are what usually stop a drive from shrinking). You'll reinstall them in SparkOS.
5. **Shrink E:** right-click Start > Disk Management > right-click **E:** > Shrink Volume. In
   "Enter the amount of space to shrink in MB" type **614400** (600 GB for SparkOS; E: keeps about
   350 GB, with WoW and `Personal Projects`). The freed space shows as black "Unallocated" on
   Disk 2. Leave it empty. If Windows offers less than 614400, something on E: can't move (often
   the Xbox app's folders, step 4); anything above 100000 MB still works, it's only less room.

## Make the USB stick (16 GB or larger, it gets erased)

1. Download **every file** of the `installer` release into one folder (the parts exist because
   GitHub limits each file to 2 GB). It is a draft, not public: signed in to GitHub, it shows on the
   repository's Releases page, or run `gh release download installer -R Wolklaw/sparkos -D <folder>`.
2. Double-click **`join-iso.cmd`**. It joins the parts into `SparkOS-installer.iso` and checks it.
   It must say "OK".
3. Write the ISO with **Fedora Media Writer** ("Select .iso file") or **Rufus** (choose
   **DD mode** when it asks).

## Install (about 20 minutes)

1. Restart with the stick in, and press **F8** while the ASUS logo shows to get the boot menu.
   Pick the USB stick (the "UEFI:" entry).
2. SparkOS starts from the stick (the live session) and shows a "SparkOS installer" window: click
   **Install SparkOS**. If it stops at a sign-in screen for "Live System User" instead (older
   installers), press Enter twice: there is no password.
3. **Welcome:** language. **Date and time:** America/Toronto (Quebec).
4. **Installation method: the most important screen.** (Names below are the installer's own
   labels, from the version in this ISO.)
   - Under **Destination**, nothing is selected yet because the PC has several disks. Click
     **Change destination**, and in **Select destination** tick **only**
     `INTEL SSDPEKNW010T9 (nvme…)`, about 1 TB: that's E: ("Games"). Leave the WD 1 TB NVMe
     (`WDC WDS100T2B0C`, C: Windows), the WD 250 GB SATA drive (`WDC WDS250G2B0A`, D: Scrap) and
     the USB stick unticked. Click **Select**.
   - Under **How would you like to install?** pick **Share disk with other operating systems**
     ("Keep current disk layout and use available space, to dual-boot"). Leave **Reclaim
     additional space** unticked.
   - Never pick **Erase data and install** (it removes every partition on the selected disk).
     If the installer says there isn't enough free space, stop: the shrink in "Before" step 5
     didn't happen. Go back to Windows rather than reclaiming space here.
   - SparkOS makes its own small EFI partition (600 MB) and its system partitions in E:'s free
     space. Your files on E: and the Windows disk aren't touched (checked byte for byte in a VM).
5. **Storage configuration:** encryption is optional (you'd type its password at every start).
6. **Create Account:** your name, user name and password.
7. **Review and install:** check that the destination says the INTEL disk only, then
   **Install**. When it's done, restart and take the stick out.
8. **Secure Boot: do this right away.** On the first start after the install, a blue "Perform MOK
   management" screen shows straight away. Choose **Enroll MOK > Continue > Yes**, type the password
   `universalblue` (Universal Blue's documented key password; it lets the SparkOS kernel start with
   Secure Boot on), then **Reboot**. It happens once.
   - If it's left alone, the PC restarts after about 5 minutes and the next start only gives
     10 seconds ("Press any key to perform MOK management"). Missed again, SparkOS won't start with
     Secure Boot on: GRUB says "bad shim signature".
   - To get the screen back: start the USB stick again, open a terminal (Konsole) and run
     `sudo mokutil --import /usr/share/ublue-os/sb_pubkey.der`, type `universalblue` twice, restart
     without the stick and enroll. (Not tried yet; this is the installer's own enrollment step.)

## First start

- The SparkOS boot splash with "Preparing System", which **restarts the PC once** by itself on the
  first start (expected, not a failure). Then the boot splash again, the sign-in screen, the zap
  sound, then **Spark Welcome**: pick your
  game launchers and apps, copy folders from Windows (it reads the Windows drive, never writes to
  it), and check graphics, sound, the printer and network.
- **Choosing Windows:** press F8 at startup and pick "Windows Boot Manager". If SparkOS's own boot
  menu doesn't list Windows, that's expected for now; F8 always works.
- Then [first-day.md](first-day.md): the first update, FreeSuite, your WoW interface and the day-one checks. The app-by-app answers are in
  [switching.md](switching.md).

## If something goes wrong

- **The PC starts straight into Windows:** use F8 and pick **"Bazzite"** (that is SparkOS's entry;
  SparkOS is built on Bazzite), or set it first in the BIOS boot order (Del at the ASUS logo).
- **"bad shim signature" at startup:** the Secure Boot key wasn't enrolled; see step 8 of "Install".
- **A bad update:** at startup, pick the previous version in SparkOS's boot menu. Updates never
  remove the version you had.
- **Windows asks for a BitLocker key:** type the recovery key from step 2 of "Before".
