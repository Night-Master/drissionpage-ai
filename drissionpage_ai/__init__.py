# -*- coding:utf-8 -*-
"""
drissionpage-ai: AI-powered web automation helpers for DrissionPage.

Importing this package patches DrissionPage's ChromiumBase with an `agent`
property and ai* shortcut methods. All page-like objects (ChromiumTab,
ChromiumPage, MixTab, WebPage, ChromiumFrame) inherit from ChromiumBase,
so one patch covers every object users get from a Chromium browser.
"""
from DrissionPage._pages.chromium_base import ChromiumBase

from .agent import DrissionPageAgent

__version__ = '0.2.0'
__all__ = ['DrissionPageAgent']

_AGENT_ATTR = '_drissionpage_ai_agent'


def _get_agent(self):
    agent = getattr(self, _AGENT_ATTR, None)
    if agent is None:
        agent = DrissionPageAgent(self)
        setattr(self, _AGENT_ATTR, agent)
    return agent


def aiAct(self, prompt, options=None):
    return _get_agent(self).aiAct(prompt, options=options)


def ai(self, prompt, options=None):
    return _get_agent(self).ai(prompt, options=options)


def aiTap(self, locate, options=None):
    return _get_agent(self).aiTap(locate, options=options)


def aiHover(self, locate, options=None):
    return _get_agent(self).aiHover(locate, options=options)


def aiInput(self, locate, value, clear=True, options=None):
    return _get_agent(self).aiInput(locate, value, clear=clear, options=options)


def aiKeyboardPress(self, locate=None, opt=None):
    return _get_agent(self).aiKeyboardPress(locate=locate, opt=opt)


def aiScroll(self, locate=None, opt=None):
    return _get_agent(self).aiScroll(locate=locate, opt=opt)


def aiDoubleClick(self, locate, options=None):
    return _get_agent(self).aiDoubleClick(locate, options=options)


def aiRightClick(self, locate, options=None):
    return _get_agent(self).aiRightClick(locate, options=options)


def aiTapAt(self, bbox, coord_type=None, options=None):
    return _get_agent(self).aiTapAt(bbox, coord_type=coord_type, options=options)


def aiDragAt(self, source_bbox, target_bbox, coord_type=None, path='curve',
             steps=None, duration=None, options=None):
    return _get_agent(self).aiDragAt(source_bbox, target_bbox, coord_type=coord_type,
                                     path=path, steps=steps, duration=duration, options=options)


def aiAsk(self, prompt, options=None):
    return _get_agent(self).aiAsk(prompt, options=options)


def aiQuery(self, data_demand, options=None):
    return _get_agent(self).aiQuery(data_demand, options=options)


def aiQueryImages(self, prompt, options=None):
    return _get_agent(self).aiQueryImages(prompt, options=options)


def aiBoolean(self, prompt, options=None):
    return _get_agent(self).aiBoolean(prompt, options=options)


def aiNumber(self, prompt, options=None):
    return _get_agent(self).aiNumber(prompt, options=options)


def aiString(self, prompt, options=None):
    return _get_agent(self).aiString(prompt, options=options)


def aiAssert(self, assertion, error_msg=None, options=None):
    return _get_agent(self).aiAssert(assertion, error_msg=error_msg, options=options)


def aiLocate(self, locate, options=None):
    return _get_agent(self).aiLocate(locate, options=options)


def aiWaitFor(self, assertion, options=None):
    return _get_agent(self).aiWaitFor(assertion, options=options)


def runYaml(self, yaml_script_content):
    return _get_agent(self).runYaml(yaml_script_content)


def setAIActContext(self, ai_act_context):
    return _get_agent(self).setAIActContext(ai_act_context)


def evaluateJavaScript(self, script):
    return _get_agent(self).evaluateJavaScript(script)


def recordToReport(self, title=None, options=None):
    return _get_agent(self).recordToReport(title=title, options=options)


def freezePageContext(self):
    return _get_agent(self).freezePageContext()


def unfreezePageContext(self):
    return _get_agent(self).unfreezePageContext()


def _install():
    ChromiumBase.agent = property(_get_agent)
    for name in ('aiAct', 'ai', 'aiTap', 'aiHover', 'aiInput', 'aiKeyboardPress',
                 'aiScroll', 'aiDoubleClick', 'aiRightClick', 'aiTapAt', 'aiDragAt',
                 'aiAsk', 'aiQuery', 'aiQueryImages', 'aiBoolean', 'aiNumber',
                 'aiString', 'aiAssert', 'aiLocate', 'aiWaitFor', 'runYaml',
                 'setAIActContext', 'evaluateJavaScript', 'recordToReport',
                 'freezePageContext', 'unfreezePageContext'):
        setattr(ChromiumBase, name, globals()[name])


_install()
