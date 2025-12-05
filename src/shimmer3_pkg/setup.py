from setuptools import setup, find_packages
import os
from glob import glob

package_name = 'shimmer3_pkg'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name), glob('launch/*.launch.py')),],
    install_requires=[
        'setuptools',
        'rclpy',
        'numpy',
        'heartpy',],
    zip_safe=True,
    maintainer='Wonse Jo',
    maintainer_email='wonsu0513@gmail.com',
    description='it is to read the biosignals of the shimmer3 gsr unit.',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'shimmer3_node = shimmer3_pkg.shimmer3_node:main',
            'data_processing = shimmer3_pkg.data_processing:main',
            # 'csv_writer = shimmer3_pkg.csv_writer:main',
            'raw_ppg_logger = shimmer3_pkg.csv_writer:main',
            'bpm_detector_node = shimmer3_pkg.bpm_detector:main',
            'matplotter_node = shimmer3_pkg.matplotter_node:main',
        ],},)
