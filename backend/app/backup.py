"""Non-destructive SQLite online backup. Never starts a robot or migrates data."""
import json
import os
import shutil
import sqlite3
from pathlib import Path


def backup(destination, database, configuration):
    destination=Path(destination)
    if destination.exists():raise ValueError('Backup destination must be a new directory; refusing to overwrite')
    database=Path(database).resolve()
    if not database.is_file():raise ValueError('Existing mission database required')
    destination.mkdir(parents=True)
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as source:
        with sqlite3.connect(destination/'missions.sqlite3') as target:source.backup(target)
    if Path(configuration).is_file():shutil.copyfile(configuration,destination/'robot-config.json')
    (destination/'manifest.json').write_text(json.dumps({'simulation_only':True,'schema_version':1,'note':'Stop the backend for a coherent database + configuration snapshot.'},indent=2)+'\n')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Back up existing mission/configuration data to a NEW directory')
    parser.add_argument('destination');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/'data'
    backup(args.destination,os.getenv('MISSION_DB_PATH',str(root/'missions.sqlite3')),os.getenv('ROBOT_CONFIG_PATH',str(root/'robot-config.json')))
