#!/usr/bin/env python3
"""
File: tar-smart-backup.py
Author: Evgeniy Klemin
Email: evgeniy.klemin@gmail.com
Github: https://github.com/evgeniy-klemin/tar-smart-backup
Description: Backup directory by incremental tar
"""

import argparse
import sys
import subprocess
import os
import errno
import shutil
import logging
import paramiko

logging.basicConfig(stream=sys.stdout, level=logging.ERROR)
logger = logging.getLogger(__name__)

TAR_COMMAND_BACKUP = "/bin/tar --file={filename} --listed-incremental={snap} --ignore-failed-read --one-file-system --recursion --preserve-permissions -C {source_dir_parent} -cpz {source_dir_basename}"
TAR_COMMAND_RESTORE = "/bin/tar --extract --strip-components 1 --ignore-failed-read --preserve-permissions --recursion --listed-incremental={snap} --file {filename} -C {destination_dir}"
EXT = '.tar.gz'


class DefaultHelpParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        defkwargs = {
            'formatter_class': argparse.ArgumentDefaultsHelpFormatter
        }
        defkwargs.update(kwargs)
        super(DefaultHelpParser, self).__init__(*args, **defkwargs)

    def error(self, message):
        sys.stderr.write('error: %s\n' % message)
        self.print_help()
        sys.exit(2)


def main():
    """Main"""

    parser = DefaultHelpParser(description='Backup directory.')
    parser.add_argument('name', help='Name of backup')
    parser.add_argument('--sync', action='store_true',
                        help='Sync with remote throuh ssh')
    parser.add_argument('--ssh-key-rsa', help='Private RSA key')
    parser.add_argument('--ssh-host', help='SSH host')
    parser.add_argument('--ssh-port', default=22, help='SSH port')
    parser.add_argument('--ssh-user', default='app', help='SSH port')
    parser.add_argument('--remote-dir', default='/home/app/backups',
                        help='Dir in remote backup server')

    subparsers = parser.add_subparsers(dest='action', help='Action')

    parser_backup = subparsers.add_parser('backup', help='Backup')
    parser_backup.add_argument('src', help='Directory for backup (source)')
    parser_backup.add_argument('--levels', type=int, default=4,
                               help='Max snapshot levels')
    parser_backup.add_argument('--count', type=int, default=5,
                               help='Count snapshots on each levels')
    parser_backup.add_argument('--dst', default='.', help='Where hold backups')

    parser_restore = subparsers.add_parser('restore', help='Restore')
    parser_restore.add_argument('dst', help='Directory for extract (destination)')
    parser_restore.add_argument('--src', default='.', help='Where hold backups')

    args = parser.parse_args()

    if args.action == 'backup':
        sys.exit(backup(args))
    if args.action == 'restore':
        sys.exit(restore(args))

    sys.exit(1)


def silentremove(filename):
    """Remove file if exists
    """
    try:
        os.remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def backup_full(args):
    """""Full backup

    Returns:
        int: exit code from tar
    """
    snap = "{}-snar-0".format(args.name)
    snap_path = os.path.join(args.dst, snap)
    filename = "{}.tar.gz".format(args.name)
    file_path = os.path.join(args.dst, filename)
    silentremove(snap_path)
    silentremove(file_path)
    source_dir_parent = os.path.abspath(os.path.join(args.src, os.pardir))
    source_dir_basename = os.path.basename(args.src)
    command = TAR_COMMAND_BACKUP.format(
        filename=file_path, snap=snap_path, source_dir_parent=source_dir_parent,
        source_dir_basename=source_dir_basename
    )
    logger.debug("shell command: {}".format(command))
    rc = subprocess.call(command, shell=True)
    return (rc, filename, snap)


def backup_incremental(args, levels):
    """Incremental backup

    Returns:
        int: exit code from tar
    """
    level = len(levels)
    num = levels[len(levels) - 1]
    parent_snap = "{}-snar-{}".format(args.name, level - 1)
    parent_snap = os.path.join(args.dst, parent_snap)
    snap = "{}-snar-{}".format(args.name, level)
    snap_path = os.path.join(args.dst, snap)
    old_snap = "{}-snar-{}.old".format(args.name, level)
    old_snap = os.path.join(args.dst, old_snap)

    if not os.path.isfile(snap_path):
        shutil.copyfile(parent_snap, snap_path)
    silentremove(old_snap)
    shutil.copyfile(snap_path, old_snap)

    filename = args.name
    for num in levels:
        filename += "_{:0>2}".format(num)
    filename += ".tar.gz"
    file_path = os.path.join(args.dst, filename)

    source_dir_parent = os.path.abspath(os.path.join(args.src, os.pardir))
    source_dir_basename = os.path.basename(args.src)
    command = TAR_COMMAND_BACKUP.format(
        filename=file_path, snap=snap_path, source_dir_parent=source_dir_parent,
        source_dir_basename=source_dir_basename
    )
    logger.debug("shell command: {}".format(command))
    rc = subprocess.call(command, shell=True)
    return (rc, filename, snap)


def is_snap(name, filename):
    ln = len(name)
    return filename[:ln] == name\
        and filename[ln + 1:ln + 1 + len('-snar-')] == '-snar-'


def is_arch(name, filename):
    ln = len(name)
    return filename[:len(name)] == name and filename[-len(EXT):] == EXT


def find_files(name, destination_dir):
    """Find snapshot files

    Returns:
        list
    """
    return sorted(
        filename
        for filename in os.listdir(destination_dir)
        if is_arch(name, filename)
    )


def find_snap_files(name, destination_dir):
    """Find snap files

    Returns:
        list
    """
    return sorted(
        filename
        for filename in os.listdir(destination_dir)
        if is_snap(name, filename)
    )


def parse_filename(name, filename):
    """Parse snapshot filename

    Examples:
        >>> list(parse_filename('data', 'data_01_03.tar.gz'))
        [(0, 1), (1, 3)]

    Yields:
        tuple(int, int)
    """
    item = filename[len(name) + 1:-len(EXT)]
    parts = item.split('_')
    for part_index in range(len(parts)):
        try:
            value = int(parts[part_index])
        except ValueError:
            break
        else:
            yield (part_index, value)


def scan_dir(name, destination_dir):
    """Return list of levels with max num

    Examples:

        destination_dir content:

            data.tar.gz
            data_01.tar.gz
            data_01_01.tar.gz
            data_01_02.tar.gz
            data_01_03.tar.gz

        >>> scan_dir('data', destination_dir)
        [1, 3]

        1: LEVEL-1 depth=1 num=1
        3: LEVEL-1 depth=2 num=3

    Returns:
        list
    """
    found = find_files(name, destination_dir)
    if not found:
        return None
    res = []
    for filename in found:
        for part_index, value in parse_filename(name, filename):
            if len(res) < part_index + 1:
                res.append(value)
            else:
                res[part_index] = max(res[part_index], value)
    return res


def find_files_for_delete(name, destination_dir, levels):
    """Clear old level snapshots

    Returns:
        list: List of old files for delete
    """
    found = find_files(name, destination_dir)
    res = []
    for filename in found:
        for part_index, value in parse_filename(name, filename):
            if part_index > len(levels) - 2:
                res.append(filename)
    return res


def backup(args):
    """Backup directory
    """
    levels = scan_dir(args.name, args.dst)
    create_full = False
    new_levels = list(levels) if levels else []
    old_files_for_delete = []

    if levels is None:
        create_full = True
    else:
        if not levels:
            new_levels.append(1)
        else:
            level = len(levels)
            if level < args.levels - 1:
                new_levels.append(1)
            else:
                last_num = new_levels[len(new_levels) - 1]
                while last_num > args.count - 1:
                    old_files_for_delete += find_files_for_delete(args.name,
                                                                  args.dst,
                                                                  new_levels)
                    new_levels = new_levels[:-1]
                    if new_levels:
                        last_num = new_levels[len(new_levels) - 1]
                    else:
                        create_full = True
                        break
                if new_levels:
                    new_levels[len(new_levels) - 1] += 1

    if create_full:
        logger.info("Create full backup, args: {}".format(args))
        rc, filename, snap = backup_full(args)
    else:
        logger.info("Create incremental backup, args: {}".format(args))
        rc, filename, snap = backup_incremental(args, new_levels)

    if rc == 0:
        if args.sync:
            upload_file(filename, args)
            upload_file(snap, args)
        for filename in old_files_for_delete:
            os.remove(os.path.join(args.dst, filename))
        if args.sync and old_files_for_delete:
            remote_delete(old_files_for_delete, args)
        logger.info("Backup {} successed".format(args.name))
        if args.sync:
            sync_remote(args)
    else:
        logger.error("Backup with args: {} error".format(args))

    return rc


def restore(args):
    """Restore backup to directory
    """
    if args.sync:
        download_files(args)
    found = find_files(args.name, args.src)
    if not os.path.exists(args.dst):
        os.makedirs(args.dst)
    snap = ''
    for filename in found:
        parts = list(parse_filename(args.name, filename))
        snap = "{}-snar-{}".format(args.name, len(parts))
        snap = os.path.join(args.src, snap)
        file_path = os.path.join(args.src, filename)
        command = TAR_COMMAND_RESTORE.format(
            filename=file_path, destination_dir=args.dst, snap=snap
        )
        logger.debug("Shell command: {}".format(command))
        rc = subprocess.call(command, shell=True)
        if rc != 0:
            logger.error("Restore with args: {} error".format(args))
            return rc
    logger.info("Restore {} successed".format(args.name))
    return 0


def get_ssh_client(args):
    """Get ssh client
    """
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = None
    if args.ssh_key_rsa:
        key = paramiko.RSAKey.from_private_key_file(args.ssh_key_rsa)
    c.connect(hostname=args.ssh_host, username=args.ssh_user,
              port=args.ssh_port, pkey=key)
    return c


def upload_file(filename, args):
    """Upload new file to remote server through sftp
    """
    with get_ssh_client(args) as c:
        with c.open_sftp() as sftp:
            localpath = os.path.join(args.dst, filename)
            remotepath = os.path.join(args.remote_dir, filename)
            sftp.put(localpath, remotepath)
    logger.info("Upload file {} successed".format(filename))


def remote_delete(files, args):
    """Delete files on remote server
    """
    with get_ssh_client(args) as c:
        files_for_args = ' '.join([
            os.path.join(args.remote_dir, filename)
            for filename in files
        ])
        command = "rm -f {}".format(files_for_args)
        stdin, stdout, stderr = c.exec_command(command)
        stdin.close()
    logger.info("Delete remote files {} successed".format(files))


def remote_find_files(client, args):
    name = args.name
    command = "ls -1 {}".format(args.remote_dir)
    logger.debug("SSH command: {}".format(command))
    stdin, stdout, stderr = client.exec_command(command)
    stdin.close()
    res = stdout.read()
    logger.debug("SSH result: {}".format(res.splitlines()))
    files = res.splitlines()
    arch_files = sorted(
        filename for filename in files if is_arch(name, filename)
    )
    snap_files = sorted(
        filename for filename in files if is_snap(name, filename)
    )
    return arch_files + snap_files


def download_files(args):
    """Download backup files from remote server through sftp
    """
    name = args.name
    with get_ssh_client(args) as c:
        found = remote_find_files(c, args)
        with c.open_sftp() as sftp:
            for filename in found:
                remotepath = os.path.join(args.remote_dir, filename)
                localpath = os.path.join(args.src, filename)
                silentremove(localpath)
                sftp.get(remotepath, localpath)
    logger.info("Download backup files successed")


def sync_remote(args):
    """Compare files in local and remote, upload if not found
    """
    with get_ssh_client(args) as c:
        remote_found = remote_find_files(c, args)
    local_found = find_files(args.name, args.dst)
    local_snap_found = find_snap_files(args.name, args.dst)

    for local_filename in local_found + local_snap_found:
        if local_filename not in remote_found:
            logger.info("Upload missing file {}".format(local_filename))
            upload_file(local_filename, args)


if __name__ == '__main__':
    main()
