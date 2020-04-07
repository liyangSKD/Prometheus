#!/usr/bin/env python
# -*- coding: utf-8 -*-

import rospy
from sensor_msgs.msg import Image
from geometry_msgs.msg import Pose, Point, Quaternion
from cv_bridge import CvBridge
from std_msgs.msg import String
import numpy as np
import cv2
import os
import yaml
import math


# 线距底边的距离，0-1，0.5表示在图像中间
# 待检测颜色，没有此颜色时，默认检测黑色
# 可选：black，red，yellow，green，blue
global line_location, line_color


camera_matrix = np.zeros((3, 3), np.float32)
distortion_coefficients = np.zeros((5,), np.float32)

rospy.init_node('color_det', anonymous=True)
# Pose.x 为检测到的误差角度，Pose.y 为检测标志位（1代表正常检测，-1代表未检测到）
pub = rospy.Publisher('/prometheus/vision/color_line_angle', Pose, queue_size=10)



def get_line_area(frame):
    global line_location, line_color
    h = frame.shape[0]
    l1 = int(h * (1 - line_location - 0.05))
    l2 = int(h * (1 - line_location))
    line_area = frame[l1:l2, :]
    return line_area


def cnt_area(cnt):
    area = cv2.contourArea(cnt)
    return area


def seg(line_area, _line_color='black'):
    if _line_color == 'black':
        hmin, smin, vmin = 0, 0, 0
        hmax, smax, vmax = 180, 255, 46
    elif _line_color == 'red':
        hmin, smin, vmin = 0, 43, 46
        hmax, smax, vmax = 10, 255, 255
    elif _line_color == 'yellow':
        hmin, smin, vmin = 26, 43, 46
        hmax, smax, vmax = 34, 255, 255
    elif _line_color == 'green':
        hmin, smin, vmin = 35, 43, 46
        hmax, smax, vmax = 77, 255, 255
    elif _line_color == 'blue':
        hmin, smin, vmin = 100, 43, 46
        hmax, smax, vmax = 124, 255, 255
    else:
        hmin, smin, vmin = 0, 0, 0
        hmax, smax, vmax = 180, 255, 46

    line_area = cv2.cvtColor(line_area, cv2.COLOR_BGR2HSV)
    line_area = cv2.inRange(line_area, (hmin, smin, vmin), (hmax, smax, vmax))

    kernel = np.ones((5, 5), np.uint8)
    line_area = cv2.morphologyEx(line_area, cv2.MORPH_OPEN, kernel)

    # cv2.MORPH_CLOSE 先进行膨胀，再进行腐蚀操作
    kernel = np.ones((5, 5), np.uint8)
    line_area = cv2.morphologyEx(line_area, cv2.MORPH_CLOSE, kernel)

    image, contours, hierarchy = cv2.findContours(line_area, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    contours.sort(key=cnt_area, reverse=True)

    if len(contours) > 0:
        x, y, w, h = cv2.boundingRect(contours[0])
        cx, cy = int(x + w/2), int(y + h/2)
        area = cnt_area(contours[0])
        return line_area, (cx, cy), area
    else:
        return line_area, (0, 0), -1


def image_callback(imgmsg):
    global line_location, line_color

    bridge = CvBridge()
    frame = bridge.imgmsg_to_cv2(imgmsg, "bgr8")
    # processing
    area_base = get_line_area(frame)
    area, cxcy, a = seg(area_base, _line_color=line_color)

    pose = Pose(Point(0, -1, 0), Quaternion(0., 0., 0., 0.))
    if a > 0:
        cv2.circle(area, (cxcy[0], cxcy[1]), 4, (0, 0, 255), -1)
        angle = (cxcy[0] - camera_matrix[0,2]) / camera_matrix[0,2] * math.atan((area.shape[1] / 2) / camera_matrix[0,0])
        pose = Pose(Point(angle, 1, 0), Quaternion(0., 0., 0., 0.))
    else:
        area, cxcy, a = seg(area_base)
        if a > 0:
            cv2.circle(area, (cxcy[0], cxcy[1]), 4, (0, 0, 255), -1)
            angle = (cxcy[0] - camera_matrix[0,2]) / camera_matrix[0,2] * math.atan((area.shape[1] / 2) / camera_matrix[0,0])
            pose = Pose(Point(angle, 1, 0), Quaternion(0., 0., 0., 0.))

    pub.publish(pose)
    # end

    h, w = frame.shape[:2]
    img_resize = 360
    if h > w:
        h = int(float(h) / w * img_resize)
        w = img_resize
    else:
        w = int(float(w) / h * img_resize)
        h = img_resize
    frame = cv2.resize(frame, (w, h))
    cv2.imshow("cap", frame)
    # cv2.imshow("area", area)
    cv2.waitKey(10)


def color_det(topic_name):
    rospy.Subscriber(topic_name, Image, image_callback)
    rospy.spin()


if __name__ == '__main__':
    global line_location, line_color

    subscriber = rospy.get_param('~subscriber', '/prometheus/camera/rgb/image_raw')
    config = rospy.get_param('~config', 'camera_param.yaml')

    # global line_location, line_color
    line_location = rospy.get_param('~line_location', 0.5)
    line_color = rospy.get_param('~line_color', 'black')    


    yaml_config_fn = os.path.dirname(os.path.abspath(__file__)) + '/../../config/' + config
    print('Input config file: {}'.format(config))

    yaml_config = yaml.load(open(yaml_config_fn))

    camera_matrix[0,0] = yaml_config['fx']
    camera_matrix[1,1] = yaml_config['fy']
    camera_matrix[2,2] = 1
    camera_matrix[0,2] = yaml_config['x0']
    camera_matrix[1,2] = yaml_config['y0']
    print(camera_matrix)

    distortion_coefficients[0] = yaml_config['k1']
    distortion_coefficients[1] = yaml_config['k2']
    distortion_coefficients[2] = yaml_config['p1']
    distortion_coefficients[3] = yaml_config['p2']
    distortion_coefficients[4] = yaml_config['k3']
    print(distortion_coefficients)

    try:
        color_det(subscriber)
    except rospy.ROSInterruptException:
        pass
