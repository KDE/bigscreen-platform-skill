# Copyright 2020 Aditya Mehra (aix.m@outlook.com).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import astral
import time
import arrow
import json
from pytz import timezone
from datetime import datetime

from mycroft.messagebus.message import Message
from mycroft.skills.core import MycroftSkill
from mycroft.util.log import LOG
from mycroft.util.parse import normalize
from mycroft import intent_file_handler

from threading import Thread, Lock


class BigscreenPlatform(MycroftSkill):
    """
        The BigscreenPlatform skill handles much of the gui activities related to
        Skill Pages timeout functionality.
    """

    def __init__(self):
        super().__init__('BigscreenPlatform')

        self.override_idle = None
        self.interaction_without_idle = True
        self.interaction_skill_id = None
        self.idle_next = 0  # Next time the idle screen should trigger
        self.idle_lock = Lock()
        self.override_set_time = time.monotonic()

        self.has_show_page = False  # resets with each handler

    def initialize(self):
        """ Perform initalization.

            Registers messagebus handlers and sets default gui values.
        """
        self.gui.register_handler(
            'mycroft.gui.screen.close', self.close_window_by_event)
        self.add_event('mycroft.gui.screen.close', self.close_window_by_event)
        self.bus.on('mycroft.gui.screen.close', self.close_window_by_event)
        self.add_event('mycroft.gui.force.screenclose', self.close_window_by_force)
        self.bus.on('mycroft.gui.force.screenclose', self.close_window_by_force)

        try:
            self.bus.on('gui.page.show', self.on_gui_page_show)
            self.bus.on('gui.page_interaction', self.on_gui_page_interaction)
        
        except:
            LOG.info('could not register on bus')

    def shutdown(self):
        self.bus.remove('gui.page.show', self.on_gui_page_show)
        self.bus.remove('gui.page_interaction', self.on_gui_page_interaction)
        self.bus.remove('mycroft.gui.screen.close', self.close_window_by_event)
        self.bus.remove('mycroft.gui.force.screenclose', self.close_window_by_force)

    def override(self, message=None):
        """Override the resting screen.
        Arguments:
            message: Optional message to use for to restore
                     the expected override screen after
                     another screen has been displayed.
        """
        self.override_set_time = time.monotonic()
        if message:
            self.override_idle = (message, time.monotonic())

    def on_gui_page_interaction(self, message):
        """ Reset idle timer to 30 seconds when page is flipped. """
        skill_id = message.data.get('skill_id')
        self.interaction_skill_id = skill_id
        if self.interaction_without_idle is False:
            self.log.info("Resetting Timeout Counter To 30 Seconds")
            self.start_idle_event(30, skid=skill_id)

    def on_gui_page_show(self, message):
        if 'BigscreenPlatform' not in message.data.get('__from', ''):
            # Some skill other than the handler is showing a page
            self.has_show_page = True

            # If a skill overrides the idle do not switch page
            override_idle = message.data.get('__idle')
            skill_id = message.data.get('__from', '')
            if override_idle is True:
                self.interaction_without_idle = True
                self.cancel_idle_event()
                self.log.info('Overriding Till Further Notice')
                self.override(message)
            elif isinstance(override_idle, int) and not (override_idle, bool) and override_idle is not False:
                # Set the indicated idle timeout
                self.log.info('Got Override With Idle Type Int')
                self.interaction_without_idle = True
                self.log.info('Overriding idle timer to'
                              ' {} seconds'.format(override_idle))
                self.start_idle_event(override_idle, skid=skill_id)
            elif (message.data['page']):
                # Set default idle screen timer
                self.log.info('Got Override Without Idle Page')
                if not isinstance(override_idle, bool) or not isinstance(override_idle, int):
                    self.interaction_without_idle = False
                    self.start_idle_event(30, skid=skill_id)

    # Manage "idle" visual state
    def cancel_idle_event(self):
        self.idle_next = 0
        self.cancel_scheduled_event('IdleCheck')

    def start_idle_event(self, offset=60, weak=False, skid=None):
        """ Start an event for showing the idle screen.

        Arguments:
            offset: How long until the idle screen should be shown
            weak: set to true if the time should be able to be overridden
        """
        with self.idle_lock:
            if time.monotonic() + offset < self.idle_next:
                self.log.info('No update, before next time')
                return

            self.log.info('Starting idle event')
            try:
                if not weak:
                    self.idle_next = time.monotonic() + offset

                self.cancel_scheduled_event('IdleCheck')
                time.sleep(0.5)
                self.schedule_event(self.close_current_window, int(offset),
                                    name='IdleCheck', data={'skill_id': skid})
                self.log.info('Closing screen in '
                              '{} seconds'.format(offset))
            except Exception as e:
                self.log.exception(repr(e))

    def close_current_window(self, message):
        if not self.interaction_without_idle:
            self.bus.emit(Message('screen.close.idle.event', 
                                  data={"skill_idle_event_id": message.data.get('skill_id')}))

    def close_window_by_event(self, message):
        self.interaction_without_idle = False
        #self.log.info("Got Screen Exit CMD")
        self.bus.emit(Message('screen.close.idle.event', 
                              data={"skill_idle_event_id": self.interaction_skill_id}))

    def close_window_by_force(self, message):
        skill_id_from_message = message.data["skill_id"]
        #self.log.info(skill_id_from_message, "sent a force close request")
        self.bus.emit(Message('screen.close.idle.event', 
                              data={"skill_idle_event_id": skill_id_from_message}))


def create_skill():
    return BigscreenPlatform()
