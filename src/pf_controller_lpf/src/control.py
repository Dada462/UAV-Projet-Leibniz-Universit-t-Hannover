#!/usr/bin/env python3
import numpy as np
import rospy
from std_msgs.msg import Float32MultiArray
from geometry_msgs.msg import TwistStamped, Vector3, PoseStamped, Point, Quaternion
from mavros_msgs.msg import PositionTarget
from numpy import pi
from controller_tools.tools import Path_3D, sawtooth
from scipy.spatial.transform import Rotation
from controller_tools.RobotStateMachine import RobotModeState
from controller_tools.ActionServer import ActionServer
from sensor_msgs.msg import Imu


class PID():
    def __init__(self):
        self.data = 0

    def __call__(self, data, bound=np.inf):
        if bound <= 0:
            raise ValueError('Bound must be positive')
        self.data = self.data+data
        self.data = np.clip(self.data, -bound, bound)


class PFController():
    def __init__(self):
        rospy.init_node('pf_controller', anonymous=True)
        rospy.Subscriber('/robot_state', Float32MultiArray, self.update_state)
        self.imuData = np.zeros(3)
        rospy.Subscriber('/mavros/imu/data', Imu, self.imuCallback)

        self.sm = RobotModeState()
        self.pathAction = ActionServer(self)
        self.pathIsComputed = False
        self.init_path()
        self.main()

    def imuCallback(self, msg):
        self.lastImuData = self.imuData
        self.imuData = np.array(
            [msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z])

    def adj(self, w):
        return np.array([[0, -w[2], w[1]], [w[2], 0, -w[0]], [-w[1], w[0], 0]])

    def adj_inv(self, A):
        return np.array([A[2, 1], A[0, 2], A[1, 0]])

    def main(self):
        speed_pub = rospy.Publisher(
            '/mavros/setpoint_velocity/cmd_vel', TwistStamped, queue_size=10)
        accel_command_pub = rospy.Publisher(
            '/mavros/setpoint_raw/local', PositionTarget, queue_size=10)
        go_home_pub = rospy.Publisher(
            '/mavros/setpoint_position/local', PoseStamped, queue_size=10)
        path_info = rospy.Publisher('/path_info', Quaternion, queue_size=10)
        f = 30
        rate = rospy.Rate(f)
        i = 0
        self.s = 0
        self.ds = 0
        s_pos = np.zeros(3)
        self.error = 0.
        last_heading = 0
        while not rospy.is_shutdown():
            if self.pathIsComputed:
                s_pos = self.path_to_follow.local_info(self.s).X
                self.pathAction.distance_to_goal = np.linalg.norm(
                    s_pos-self.state[:3])+self.path_to_follow.s_max-self.s
            if self.sm.state == 'CONTROL' and self.sm.userInput != 'HOME' and self.sm.userInput != 'WAIT' and self.pathIsComputed:
                u, heading = self.control_lpf()
                ############################## Acceleration Topic ##############################
                command = PositionTarget()
                command.header.stamp = rospy.Time().now()
                command.coordinate_frame = PositionTarget.FRAME_BODY_NED
                command.type_mask = PositionTarget.IGNORE_PX + PositionTarget.IGNORE_PY + PositionTarget.IGNORE_PZ + \
                    PositionTarget.IGNORE_VX+PositionTarget.IGNORE_VY+PositionTarget.IGNORE_VZ
                command.type_mask = command.type_mask+PositionTarget.IGNORE_YAW
                command.acceleration_or_force = Vector3(*u)
                command.yaw_rate = 0.5*sawtooth(heading-self.state[8])
                last_heading = heading
                accel_command_pub.publish(command)
                ############################## Acceleration Topic ##############################
            elif self.sm.userInput == 'HOME':
                command = PoseStamped()
                command.pose.position = Point(0, 0, 0.5)
                q = Rotation.from_euler(
                    'XYZ', [0, 0, 0], degrees=True).as_quat()
                command.pose.orientation = Quaternion(*q)
                go_home_pub.publish(command)
                self.s = self.ds = 0
            elif self.sm.userInput == 'WAIT':
                wait_pos = self.path_to_follow.local_info(
                    self.path_to_follow.s_max).X
                command = PoseStamped()
                command.pose.position = Point(*wait_pos)
                q = Rotation.from_euler(
                    'XYZ', [0, 0, last_heading], degrees=False).as_quat()
                command.pose.orientation = Quaternion(*q)
                go_home_pub.publish(command)
                self.ds = 0
            elif self.sm.state == 'HOVERING' or self.sm.state == 'STOPPING':
                speed_pub.publish(TwistStamped())
                self.s = self.ds = 0
            path_info.publish(Quaternion(*s_pos, self.error))
            self.s = self.s+1/f*self.ds
            self.s = max(0, self.s)
            i += 1
            rate.sleep()

    def init_path(self, points=[], speeds=[], headings=[]):
        if len(points) != 0:
            try:
                self.path_to_follow = Path_3D(
                    points, speeds=speeds, headings=headings, type='waypoints')
                self.pathIsComputed = True
            except:
                print('[ERROR] Path properties were not possible to compute [ERROR]')
        self.s = 0
        self.ds = 0

    def control_lpf(self):
        # Robot state
        X = self.state[0:3]
        Vr = self.state[3:6]
        s = self.s
        wr = self.state[9:12]
        dt = 1/30

        Rm = Rotation.from_euler(
            'XYZ', angles=self.state[6:9], degrees=False).as_matrix()
        dRm = Rm@self.adj(wr)

        X = X+3*dt*Rm@Vr
        s = s+3*self.ds*dt
        Rm = Rm+3*dRm*dt
        # Path properties
        F = self.path_to_follow.local_info(s)
        Rpath = F.R

        Rtheta = Rpath.T@Rm
        # Error and its derivatives
        e = Rpath.T@(X-F.X)
        s1, y1, w1 = e
        ks = 1.5
        ds = (Rtheta@Vr)[0]+ks*s1
        if s < 0.05 and ds < 0:
            ds = 0
        self.ds = ds
        dRpath = F.dR*ds
        dRtheta = dRpath.T@Rm+Rpath.T@dRm

        S = np.array([F.k2*w1+F.k1*y1-1, -F.k1*s1, -F.k2*s1])  # PTF
        de = Vp+ds*S
        ds1, dy1, dw1 = de

        Vpath, k0, k1, kpath, _, c1, amax = 0.5, 1.5, 1.5, 0.4, 1.5, 50, 0.5
        nu_d = F.speed
        heading = F.heading

        e = np.array([s1, y1, w1])

        e1 = np.array([0, y1, w1])
        de1 = np.array([0, dy1, dw1])
        self.error = 100*np.linalg.norm(e, ord=np.inf)
        speed = np.linalg.norm(Vr)
        self.speed = speed

        s = np.linspace(s, s+k0, 250)
        Fahead = self.path_to_follow.local_info(s)
        Cahead = np.max(Fahead.C)
        a = np.sqrt(1/(1e-6+Cahead))
        a = np.clip(a, 0.25, 1.75)
        nu_d = np.clip(nu_d, 0.25, a)

        # vplin = (Rtheta@Vr)[0]
        d_path = np.linalg.norm(e1/kpath)
        ve = nu_d*(1-np.tanh(d_path))
        dve = -nu_d/kpath*(1-np.tanh(d_path)**2)*de1@e1/(1e-6+d_path)
        if ((self.path_to_follow.s_max-self.s) < nu_d*2):
            ve = np.clip(self.path_to_follow.s_max-self.s, -0.5, 0.5)
            dve = -np.clip(ds, -0.5, 0.5)*(np.abs(ds) <= 0.5)
        Vp = -Vpath*np.tanh(e1/kpath)+np.array([ve, 0, 0])

        Rd = Rotation.from_euler(
            'XYZ', angles=self.state[6:9], degrees=False).as_matrix()
        data = Rd@self.imuData
        Rd1 = Rotation.from_euler(
            'XYZ', [0, 0, self.state[8]], degrees=False).as_matrix()
        data = Rd1.T@data
        data[2] = data[2]-9.81

        dVp = -Vpath/kpath*(1-np.tanh(e1/kpath)**2)*de1+np.array([dve, 0, 0])

        Vd = Rtheta.T@Vp
        dVd = dRtheta.T@Vp+Rtheta.T@dVp
        dVr = dVd+k1*(Vd-Vr)
        dVr = dVr+self.adj(wr)@Vr
        dVr = np.tanh(dVr/3)*3
        self.last_dVr = dVr

        angle = np.tanh(F.dC/c1)*amax
        r = Rotation.from_rotvec(F.w1*angle)
        dVr = r.apply(dVr)
        return dVr, heading

    def update_state(self, data):
        self.state = np.array([*data.data])


if __name__ == '__main__':
    try:
        C = PFController()
    except rospy.ROSInterruptException:
        pass
