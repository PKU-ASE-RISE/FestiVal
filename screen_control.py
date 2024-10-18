# -*- coding: utf-8 -*-
"""
安卓手机操控
"""
import logging
import uiautomator2 as u2
import time
import os
import random
import cv2
import base64

class AndroidController:
    """
    安卓手机控制
    """
    def __init__(self, port):
        self.device = u2.connect_usb(port)
        self.upperbar = 0
        self.subbar = 0
        self.sleep_time = 0.1
        if not self.device:
            logging.error('init Android opr failed!')
        else:
            logging.info('init Android opr success!')
        # self.device.set_fastinput_ime(True)
    def start_app(self, app_pkg_name,wait=2):
        """
        启动app
        :param app_pkg_name:
        :return:
        """
        # 每次打开前先关闭，同时保证处在消息界面
        try:
            self.stop_app(app_pkg_name)
        except:
            pass
        self.device.app_start(app_pkg_name)
        logging.debug('start app begin...')
        time.sleep(wait)
        # self.device.set_fastinput_ime(True)
        logging.debug('start app end...')


    def stop_app(self, app_pkg_name):
        """
        app杀进程
        :param app_pkg_name:
        :return:
        """
        self.device.app_stop(app_pkg_name)

    def click(self, x, y,wait_time = 0.1):
        """
        点击坐标（x,y）
        :param x:
        :param y:
        :return:
        """
        if(x<0 and y < 0):
            self.back()
            return
        self.device.click(int(x), int(y)+self.upperbar)
        time.sleep(wait_time)

    def home(self):
        """
        home键
        :return:
        """
        self.device.press("home")

    def back(self):
        """
        返回键
        :return:
        """
        self.device.press("back")
        time.sleep(self.sleep_time)
    def tap_hold(self, x, y, t):
        """
        长按,持续t秒
        :param x:
        :param y:
        :param t:
        :return:
        """
        self.device.long_click(int(x), int(y)+self.upperbar, t)
        time.sleep(self.sleep_time)
    def vertical_scroll(self,start=250,end=1000,direction = 1):
        if direction==1:
            self.swipe(600,start,600,end)
        else:
            self.swipe(600,end,600,start)
    def horizontal_scroll(self,start = 200,end = 800,pos=500,direction = 1):
        if direction==1:
            self.swipe(start,pos,end,pos)
        else:
            self.swipe(end,pos,start,pos)
    def swipe(self,fx,fy,tx,ty,steps=40):
        self.device.swipe(int(fx),int(fy),int(tx),int(ty),steps=steps)
        time.sleep(self.sleep_time)

    def input(self, text = "PKU", clear=True):
        try:
            # TODO: deal with clear here
            print(text)
            text = text.replace(" ","\ ")
            os.system("adb shell input text \"{}\"".format(text))
            time.sleep(0.2)
            # self.device.send_keys(text,clear=clear)
        except:
            return False
        return True

    def capture_screen(self):
        """
        截屏
        :return:
        """
        image = self.device.screenshot(format='opencv')
        image = image[self.upperbar:] # shiver the task bar
        return image
    def dump(self):
        return self.device.dump_hierarchy()
    def app_info(self):
        CurApp = self.device.app_current()
        return CurApp['package'],CurApp['activity']

if __name__ == "__main__":
    print(AndroidController("emulator-5554").dump())
