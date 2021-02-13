from flask import Flask, render_template, request, redirect
from os.path import isfile, join
from sys import platform, argv
from threading import Thread
from sqlite3 import Error
import urllib.parse
import webbrowser
import threading
import requests
import datetime
import unittest
import sqlite3
import math
import json
import time
import csv
import sys
import os
import re
import virtualbox
from virtualbox import library

app = Flask(__name__, template_folder='./front-end', static_folder='./front-end', static_url_path='')
vbox = virtualbox.VirtualBox()
sessions = []
ips = []


def getVM(name=''):
    if name:
        return vbox.find_machine(name)
    else:
        return vbox.machines

def getState(x):
    return {
        'FirstOnline': True,
        'Restoring': True,
        'Starting': True,
        'Saved': False,
        'Stopping': False,
        'PoweredOff': False,
        'Aborted': False
    }[x]
    
def prepareVMs():
    vms = []
    allVms = getVM()
    for vm in allVms:
        state = 'none'
        # print(str(vm.state))
        state = getState(str(vm.state))
        uid_name = str(vm.name).replace(' ', '_').replace('(', '').replace(')', '')
        cpu_count =  str(vm.cpu_count)
        memory_size =  str(vm.memory_size)
        memory_usage = int(memory_size) * 100 / 16000
        vms.append([vm.name, state, uid_name, memory_size, cpu_count, memory_usage])
    return vms

def runSsh(session):
    try:
        print('starting ssh service ...')
        guest_session = session.console.guest.create_session("ubuntu1", "1234")
        proc, stdout, stderr = guest_session.execute("/home/ubuntu1/.local/bin/wssh")
    except:
        pass

def retriveIpAddress(name, session):
    try:
        print('retriving ip address ...')
        guest_session = session.console.guest.create_session("ubuntu1", "1234")
        proc, stdout, stderr = guest_session.execute("/sbin/ifconfig")
        print('stdout: ', stdout.decode('ascii'))
        print('stderr: ', stderr.decode('ascii'))
        ip = re.findall( r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", stdout.decode('ascii'))[0]
        print('ip: ', ip)
        ips.append([name, ip])
    except:
        pass

def getSession(name, remove = False):
    if name:
        for session in sessions:
            if session[0] == name:
                if remove:
                    session[0] = ''
                return session[1]

def getIpAddress(name, remove = False):
    if name:
        for ip in ips:
            if ip[0] == name:
                if remove:
                    ip[0] = ''
                return ip[1]
            
def cloneVM(origin_vm, snapshot_name_or_id=None,
              mode=library.CloneMode.machine_state,
              options=None, name=None,
              uuid=None, groups=None, basefolder='', register=True):
        """Clone this Machine
        Options:
            snapshot_name_or_id - value can be either ISnapshot, name, or id
            mode - set the CloneMode value
            options - define the CloneOptions options
            name - define a name of the new VM
            uuid - set the uuid of the new VM
            groups - specify which groups the new VM will exist under
            basefolder - specify which folder to set the VM up under
            register - register this VM with the server
        Note: Default values create a linked clone from the current machine state
        Return a IMachine object for the newly cloned vm
        """
        if options is None:
            # options = [library.CloneOptions.keep_disk_names]
            options = [library.CloneOptions.link]
            # options = [library.CloneOptions.keep_natma_cs]
        if groups is None:
            groups = []

        if snapshot_name_or_id is not None:
            if isinstance(snapshot_name_or_id, basestring):
                snapshot = origin_vm.find_snapshot(snapshot_name_or_id)
            else:
                snapshot = snapshot_name_or_id
            vm = snapshot.machine
        else:
            # linked clone can only be created from a snapshot...
            # try grabbing the current_snapshot
            if library.CloneOptions.link in options:
                vm = origin_vm.current_snapshot.machine
            else:
                vm = origin_vm

        if name is None:
            name = "%s Clone" % vm.name

        # Build the settings file
        create_flags = ''
        if uuid is not None:
            create_flags = "UUID=%s" % uuid
        primary_group = ''
        if groups:
            primary_group = groups[0]

        # Make sure this settings file does not already exist
        test_name = name
        settings_file = ''
        for i in range(1, 1000):
            settings_file = vbox.compose_machine_filename(test_name,
                                                          primary_group,
                                                          create_flags,
                                                          basefolder)
            if not os.path.exists(os.path.dirname(settings_file)):
                break
            test_name = "%s (%s)" % (name, i)
        name = test_name

        # Create the new machine and clone it!
        vm_clone = vbox.create_machine(settings_file, name, groups, '', create_flags)
        progress = vm.clone_to(vm_clone, mode, options)
        progress.wait_for_completion(-1)

        if register:
            vbox.register_machine(vm_clone)
        return vm_clone

@app.route('/')
def indexPage():
    vms = prepareVMs()
    return render_template('/index.html', vms=vms)

@app.route('/start', methods=['GET'])
def start():
    name = str(request.args.get('name'))
    session = virtualbox.Session()
    progress = getVM(name).launch_vm_process(session, "gui", [])
    progress.wait_for_completion(-1)
    sessions.append([name, session])
    return redirect('/')

@app.route('/stop', methods=['GET'])
def stop():
    name = str(request.args.get('name'))
    session = virtualbox.Session()
    getVM(name).lock_machine(session, library.LockType.shared)
    session.console.power_down()
    return redirect('/')

@app.route('/clone', methods=['GET'])
def clone():
    name = str(request.args.get('name'))
    clone_name = str(request.args.get('clone_name'))
    cloneVM(getVM(name), name = clone_name)
    return redirect('/')

@app.route('/terminal', methods=['GET'])
def terminal():
    name = str(request.args.get('name'))
    session = virtualbox.Session()
    getVM(name).lock_machine(session, library.LockType.shared)
    retriveIpAddress(name, session)
    t1 = threading.Thread(target=runSsh, args=(session,))
    t1.start()
    # session = getSession(name)
    # t2 = threading.Thread(target=retriveIpAddress, args=(name, session,))
    # t2.start()
    ip = getIpAddress(name)
    print('gathered ip: ', str(ip))
    terminal_address = 'http://' + str(ip) + ':8888/?hostname=ubuntu1-VirtualBox&username=ubuntu1&password=MTIzNA=='
    session.unlock_machine()
    return terminal_address

@app.route('/setting', methods=['GET'])
def setting():
    name = str(request.args.get('name'))
    memory = str(request.args.get('memory'))
    cpu = str(request.args.get('cpu'))
    session = virtualbox.Session()
    getVM(name).lock_machine(session, library.LockType.shared)
    vm = session.machine
    vm.memory_size = int(memory)
    vm.cpu_count = int(cpu)
    vm.save_settings()
    session.unlock_machine()
    return redirect('/')

@app.route('/remove', methods=['GET'])
def remove():
    name = str(request.args.get('name'))
    vm = getVM(name)
    if vm.state >= library.MachineState.running:
        session = virtualbox.Session()
        vm.lock_machine(session, library.LockType.shared)
        try:
            progress = session.console.power_down()
            progress.wait_for_completion(-1)
        except Exception:
            print("Error powering off machine", file=sys.stderr)
        session.unlock_machine()
        time.sleep(0.5)  # TODO figure out how to ensure session is really unlocked...

    option = library.CleanupMode.full
    media = vm.unregister(option)
    progress = vm.delete_config(media)
    progress.wait_for_completion(-1)
    media = []
    return redirect('/')

if __name__ == "__main__":
    webbrowser.open('http://localhost:3333')
    app.run(host="0.0.0.0", port=3333, threaded=True)
