#!/usr/bin/env python3
import unittest
#from unittest.mock import Mock
import tar_smart_backup
import os
import random
import shutil
import string


def random_string(len):
    return ''.join(random.choice(string.ascii_uppercase + string.digits)
                   for _ in xrange(len))

class BackupCase(unittest.TestCase):

    def create_tstfile(self, suffix, len=1024):
        filename = 'tstfile{}'.format(suffix)
        file_path = os.path.join(self.source_dir, filename)
        with open(file_path, 'w+') as f:
            f.write(random_string(len))

    def check_dirs(self):
        if not os.path.exists(self.destination_dir):
            os.makedirs(self.destination_dir)
        if not os.path.exists(self.source_dir):
            os.makedirs(self.source_dir)

    def setUp(self):
        self.backup_name = 'tst_tar_smart_backups'
        self.destination_dir = '/tmp/tar_smart_backups'
        self.source_dir = '/tmp/{}'.format(self.backup_name)
        self.parser = tar_smart_backup.create_argparse()

        args_str = '{} backup {} --dst={} --count=2 --levels=3'.format(
            self.backup_name,
            self.source_dir,
            self.destination_dir
        )
        self.args = self.parser.parse_args(args_str.split())

        # Setup
        self.check_dirs()
        self.create_tstfile('1')

    def tearDown(self):
        shutil.rmtree(self.destination_dir)
        shutil.rmtree(self.source_dir)

    def find_files(self):
        return tar_smart_backup.find_files(self.backup_name,
                                           self.destination_dir)

    def filename(self, suffix):
        return '{}{}.tar.gz'.format(self.backup_name, suffix)

    def test_backup(self):
        tar_smart_backup.backup(self.args)
        self.assertEqual(self.find_files(), [
            self.filename('')
        ])
        tar_smart_backup.backup(self.args)
        self.assertEqual(self.find_files(), [
            self.filename(''),
            self.filename('_01')
        ])
        tar_smart_backup.backup(self.args)
        self.assertEqual(self.find_files(), [
            self.filename(''),
            self.filename('_01'),
            self.filename('_01_01')
        ])
        tar_smart_backup.backup(self.args)
        self.assertEqual(self.find_files(), [
            self.filename(''),
            self.filename('_01'),
            self.filename('_01_01'),
            self.filename('_01_02')
        ])
        tar_smart_backup.backup(self.args)
        self.assertEqual(self.find_files(), [
            self.filename(''),
            self.filename('_01'),
            self.filename('_02')
        ])
