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

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
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
    """main"""

    parser = DefaultHelpParser(description='Backup directory.')
    parser.add_argument('name', help='Name of backup')

    subparsers = parser.add_subparsers(dest='action', help='Action')

    parser_backup = subparsers.add_parser('backup', help='Backup')
    parser_backup.add_argument('src', help='Directory for backup (source)')
    parser_backup.add_argument('--levels', type=int, default=3,
                               help='Max snapshot levels')
    parser_backup.add_argument('--count', type=int, default=10,
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
    try:
        os.remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def backup_level0(args):
    snap = "{}-snar-0".format(args.name)
    snap = os.path.join(args.dst, snap)
    filename = "{}.tar.gz".format(args.name)
    filename = os.path.join(args.dst, filename)
    silentremove(snap)
    silentremove(filename)
    source_dir_parent = os.path.abspath(os.path.join(args.src, os.pardir))
    source_dir_basename = os.path.basename(args.src)
    command = TAR_COMMAND_BACKUP.format(
        filename=filename, snap=snap, source_dir_parent=source_dir_parent,
        source_dir_basename=source_dir_basename
    )
    logger.debug("shell command: {}".format(command))
    return subprocess.call(command, shell=True)


def backup_levelN(args, levels):
    level = len(levels)
    num = levels[len(levels) - 1]
    parent_snap = "{}-snar-{}".format(args.name, level - 1)
    parent_snap = os.path.join(args.dst, parent_snap)
    snap = "{}-snar-{}".format(args.name, level)
    snap = os.path.join(args.dst, snap)
    old_snap = "{}-snar-{}.old".format(args.name, level)
    old_snap = os.path.join(args.dst, old_snap)

    if not os.path.isfile(snap):
        shutil.copyfile(parent_snap, snap)
    silentremove(old_snap)
    shutil.copyfile(snap, old_snap)

    filename = args.name
    for num in levels:
        filename += "_{:0>2}".format(num)
    filename += ".tar.gz"
    filename = os.path.join(args.dst, filename)

    source_dir_parent = os.path.abspath(os.path.join(args.src, os.pardir))
    source_dir_basename = os.path.basename(args.src)
    command = TAR_COMMAND_BACKUP.format(
        filename=filename, snap=snap, source_dir_parent=source_dir_parent,
        source_dir_basename=source_dir_basename
    )
    logger.debug("shell command: {}".format(command))
    return subprocess.call(command, shell=True)


def find_files(name, destination_dir):
    """Find snapshot files"""
    return sorted(
        filename
        for filename in os.listdir(destination_dir)
        if filename[:len(name)] == name and filename[-len(EXT):] == EXT
    )


def parse_filename(name, filename):
    """""Parse snapshot filename

    Example:
        >>> parse_filename('data', 'data_01_03.tar.gz') -> [(0, 1), (1, 3)]

    Return:
        generator(tuple(int, int))
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
    """""Return list of levels with max num

    Example:

        destination_dir content:

            data.tar.gz
            data_01.tar.gz
            data_01_01.tar.gz
            data_01_02.tar.gz
            data_01_03.tar.gz

        >>> scan_dir('data', destination_dir) -> [1, 3]

        1: LEVEL-1 depth=1 num=1
        3: LEVEL-1 depth=2 num=3

    Return:
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


def clear_old(name, destination_dir, levels):
    """Clear old level snapshots"""
    found = find_files(name, destination_dir)
    for_delete = []
    for filename in found:
        for part_index, value in parse_filename(name, filename):
            if part_index > len(levels) - 2:
                for_delete.append(filename)
    for filename in for_delete:
        os.remove(os.path.join(destination_dir, filename))


def backup(args):
    levels = scan_dir(args.name, args.dst)
    create_full = False
    new_levels = list(levels) if levels else []

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
                    clear_old(args.name, args.dst, new_levels)
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
        rc = backup_level0(args)
    else:
        logger.info("Create incremental backup, args: {}".format(args))
        rc = backup_levelN(args, new_levels)
    if rc != 0:
        logger.error("Backup with args: {} error".format(args.dst))
    return rc


def restore(args):
    found = find_files(args.name, args.src)
    if not os.path.exists(args.dst):
        os.makedirs(args.dst)
    snap = ''
    for filename in found:
        parts = list(parse_filename(args.name, filename))
        snap = "snar-{}".format(len(parts))
        snap = os.path.join(args.src, snap)
        file_path = os.path.join(args.src, filename)
        command = TAR_COMMAND_RESTORE.format(
            filename=file_path, destination_dir=args.dst, snap=snap
        )
        logger.debug("shell command: {}".format(command))
        rc = subprocess.call(command, shell=True)
        if rc != 0:
            logger.error("Restore from {}, {} to {} error".format(file_path,
                                                                  snap,
                                                                  args.dst))
            return rc
    logger.info("Restore backup in {} successed".format(args.dst))
    return 0


if __name__ == '__main__':
    main()
