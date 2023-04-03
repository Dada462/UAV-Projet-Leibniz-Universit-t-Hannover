#!/usr/bin/env python
import numpy as np
import rospy
from std_msgs.msg import Float32MultiArray
from geometry_msgs.msg import TwistStamped,Vector3,PoseStamped,Point,Vector3Stamped,Quaternion
from mavros_msgs.msg import PositionTarget,AttitudeTarget
from numpy import cos, sin, tanh, pi
import threading
from tools_3D import Path_3D,R,sawtooth
from MissionDisplayer3D import MainWindow
from pyqtgraph.Qt import QtCore, QtWidgets, QtGui
import sys
from scipy.spatial.transform import Rotation
from scipy import signal
import matplotlib.pyplot as plt
from time import time
from scipy.linalg import expm,logm

class PID():
    def __init__(self):
        self.I=0

class PFController():
    def __init__(self):
        rospy.init_node('pf_controller', anonymous=True)
        rospy.Subscriber('/robot_state', Float32MultiArray, self.update_state)
        self.state=np.zeros(12)
        self.init_path()
        
        app = QtWidgets.QApplication(sys.argv)
        self.displayer=MainWindow(self)

        ros_thread = threading.Thread(target=self.main,daemon=True)
        ros_thread.start()

        sys.exit(app.exec_())
    
    def adj(self,w):
        return np.array([[0,-w[2],w[1]] , [w[2],0,-w[0]] , [-w[1],w[0],0]])

    def adj_inv(self,A):
        return np.array([A[2,1],A[0,2],A[1,0]])
    
    def main(self):
        command_pub = rospy.Publisher('/mavros/setpoint_velocity/cmd_vel', TwistStamped, queue_size=10)
        accel_command_pub = rospy.Publisher('/mavros/setpoint_raw/local', PositionTarget, queue_size=10)
        attitude_pub = rospy.Publisher('/mavros/setpoint_raw/attitude', AttitudeTarget, queue_size=10)
        go_home_pub = rospy.Publisher('/mavros/setpoint_position/local', PoseStamped, queue_size=10)
        f=20
        rate = rospy.Rate(f)
        i=0
        self.PID=PID()
        while not rospy.is_shutdown():
            s_pos=self.path_to_follow.local_info(self.s).X
            self.displayer.update_state(self.state,s_pos)
            u=self.PLF_3D_Kin()

            if self.displayer.mission_state['start']:
                # Kin Lyapunov PF
                command=TwistStamped()
                command.twist.linear=Vector3(*u)
                command.twist.angular=Vector3(0.,0.,0)
                command_pub.publish(command)
                

                # Dyn Lyapunov PF
                # command = PositionTarget()
                # command.header.stamp=rospy.Time().now()
                # command.coordinate_frame = PositionTarget.FRAME_BODY_NED
                # command.type_mask = PositionTarget.IGNORE_PX + PositionTarget.IGNORE_PY + PositionTarget.IGNORE_PZ
                # command.acceleration_or_force=Vector3(u[0],u[1],0.)
                # command.yaw=u[2]
                # accel_command_pub.publish(command)
                
                # msg = AttitudeTarget()
                # msg.type_mask=AttitudeTarget.IGNORE_ATTITUDE
                # msg.thrust=0.5
                # msg.body_rate=Vector3(*u)
                # attitude_pub.publish(msg)


                # # Speed control
                # u=self.speed_control()
                # msg = AttitudeTarget()
                # msg.type_mask=AttitudeTarget.IGNORE_ATTITUDE
                # msg.thrust=0.5
                # msg.body_rate=Vector3(*u)
                # attitude_pub.publish(msg)
                
                # # Join a point
                # T=20
                # t=i/f
                # # P=signal.square(2 * np.pi * t/(2*T))*np.array([-1,1])*10
                # P=R(2 * np.pi * t/T)[:,0]*10
                # command=PoseStamped()
                # command.pose.position=Point(*P,10)
                # go_home_pub.publish(command)
               
                # # Using point joining of the FC
                # command=PoseStamped()
                # command.pose.position=Point(*s_pos,10)
                # go_home_pub.publish(command)
            
            elif self.displayer.mission_state['keyboard']:
                key=np.array([self.displayer.keyboard]).reshape(-1,2)
                D=np.array([[0,-1,0],[1,0,0],[0,0,-1]])
                u=0.2*D@(key[:,0]-key[:,1])
                msg = AttitudeTarget()
                msg.type_mask=AttitudeTarget.IGNORE_ATTITUDE
                
                msg.thrust=0.5
                w=self.state[6:9]
                w[2]=0
                msg.body_rate=Vector3(*2*(u-w)[:2],0)
                attitude_pub.publish(msg)
            else:
                command=PoseStamped()
                command.pose.position=Point(0,0,10)
                go_home_pub.publish(command)
            self.s=self.s+1/f*self.ds
            self.s=max(0,self.s)
            i+=1
            rate.sleep()
    
    def init_path(self):
        # self.path_to_follow=Path(lambda t : 5*np.array([cos(t),sin(2*t)]),[0,15],type='parametric')
        # self.path_to_follow=Path(lambda t : 5*np.array([cos(t),sin(0.9*t)]),[-10,10],type='parametric')
        # self.path_to_follow=Path(lambda t : 10*np.array([cos(t),sin(t)]),[-10,10],type='parametric')
        # self.path_to_follow=Path(lambda t : 10*(2+sin(10*t))*np.array([cos(t),sin(t)]),[-10,10],type='parametric')
        # self.path_to_follow=Path(lambda t : np.array([t,-10+t*0]),[-20,20],type='parametric')
        self.path_to_follow=Path_3D(lambda t : np.array([5*cos(t),5*sin(t),3*(t+10)+2]),[-10,10],type='parametric')
        
        self.s=0
        self.vars=10,1,1
    
    def update_state(self,data):
        speed=data.data[3:6]
        r = Rotation.from_euler('XYZ', data.data[6:9],degrees=False)
        r2=Rotation.from_euler('XYZ',[0,0,-data.data[9]],degrees=False)
        speed=r.apply(speed)
        speed=r2.apply(speed)
        self.state=np.array([*data.data])
        self.state[3:6]=speed
    
    def speed_control(self):
        V=self.state[3:6]
        w=self.state[6:9]
        Vd=np.array([0.3,0,0])
        k=0.2
        wd=k*np.tanh(Vd-V)
        # print(wd)
        D=np.array([[0,-1,0],[1,0,0],[0,0,0]])
        wd=D@wd
        return 2*(wd-w)
    
    def LPF_control_kin(self,x):
        X = x[0:2]
        theta_m = x[4]
        s = self.s
        # F = path_info_update(self.path_to_follow, s)
        F=self.path_to_follow.local_info(s)
        theta_c = F.psi
        theta = sawtooth(theta_m-theta_c)
        s1, y1 = R(theta_c).T@(X-F.X)
        # psi_a,Kdy1=self.vars
        Kdy1=0.5
        psi_a=pi/2
        delta = -psi_a*tanh(Kdy1*y1)
        beta=sawtooth(delta-theta)
        
        psi = delta
        nu=0.5
        ks = 1
        ds = cos(psi)*nu + ks*s1
        # theta_m_d=-pi/4
        # dtheta_m_d=0
        # k2=1
        # dtheta_m=dtheta_m_d+k2*sawtooth(theta_m_d-theta_m)
        u,v=nu*cos(beta),nu*sin(beta)
        self.ds=ds
        return np.array([u,v,0])
    
    def LPF_control_dyn(self):
        X = self.state[0:2]
        Vt = self.state[3:5]
        s = self.s
        theta_m, dtheta_m = self.state[8],self.state[11]
        u, v = Vt
        nu = np.linalg.norm(Vt)
        beta=np.arctan2(v,u)

        # print('Speed:',np.round(nu,2))
        
        # F = path_info_update(self.path_to_follow, s)
        F=self.path_to_follow.local_info(s)

        theta_c = F.psi
        s1, y1 = R(theta_c).T@(X-F.X)
        theta = sawtooth(theta_m-theta_c)
        psi = sawtooth(theta+beta)

        ks = 0.7
        ds = cos(psi)*nu + ks*s1
        self.ds=ds
        # return 0
        dtheta_c = F.C*ds
        ds1, dy1 = R(theta)@Vt-ds*np.array([1-F.C*y1, F.C*s1])

        psi_a=1.3
        y10,k1,k2,k3,k4,k5=1.25,1.5,1.8,0.07,3,1
        delta = -psi_a*tanh(y1/y10)
        ddelta = -psi_a*(1-tanh(y1/y10)**2)*dy1/y10
        dpsi=ddelta+k2*sawtooth(delta-psi)
        dbeta=dpsi-dtheta_m+dtheta_c

        nu_d=1
        dnu=k1*(nu_d-nu)
        # theta_m_d=pi/4
        # dtheta_m_d=0
        # ddtheta_m_d=0
        # ddtheta_m=ddtheta_m_d+2*(dtheta_m_d-dtheta_m)+1*(theta_m_d-theta_m)
        # dbeta=-0.25*beta
        # dnu=(2-nu)
        C=R(beta,'z')@np.array([dnu,nu*dbeta,0])
        w=self.state[6:9]
        # k=0.07
        wd=k3*np.tanh(C/k5)
        # D=np.array([[0,-1,0],[1,0,0],[0,0,0]])
        D=np.array([[0,-1,0],[1,0,0],[0,0,0]])
        wd=D@wd
        u=k4*(wd-w)
        # self.displayer.data_to_plotx.append(time())
        # self.displayer.data_to_ploty1.append(self.imu_data[-1])
        # self.displayer.data_to_ploty1.append(self.state[7])
        # self.displayer.data_to_ploty2.append(self.state[8])
        return u

    def PLF_3D_Kin(self):
        X = self.state[:3]
        s=self.s

        F=self.path_to_follow.local_info(s)
        Rpath=np.vstack((F.s1,F.y1,F.w1)).T
        s1, y1, w1 = Rpath.T@(X-F.X)
        
        
        psi_a=pi/2
        e=np.array([s1,y1,w1])
        cross_e=np.cross(np.array([1,0,0]),e)
        k_delta=0.5
        delta=-psi_a*np.tanh(k_delta*cross_e)
        Rpsi=expm(self.adj(delta))
        Rs=Rpath@Rpsi
        nu=1
        Vr=Rs@np.array([nu,0,0])

        ks=3
        ds = (np.array([nu,0,0])@Rpsi)[0]+ks*s1
        self.ds=ds

        dX=Vr
    
        return dX
    
    def LPF_control_3D(self):
        X = self.state[0:3]
        Vr = self.state[3:6]
        s = self.s
        phi,theta,psi=self.state[6:9]
        wr=self.state[9:12]
        # wr=np.flip(wr)

        Rm=Rotation.from_euler('xyz',angles=[self.state[6:9]])
        dRm=Rm.T@self.adj(wr)
        
        u, v, w = Vr
        nu = np.linalg.norm(Vr)
        beta=np.arctan2(v,u)
        gamma=np.arcsin(w/v)
        Rs=R(beta,'z')@R(gamma,'y')

        
        F=self.path_3D.local_info(s)
        Rpath=np.vstack((F.s1,F.y1,F.w1)).T
        dRpath=F.dR
        
        Rtheta = Rpath.T@Rm
        Rpsi=Rtheta@Rs
        
        dRtheta=dRpath.T@Rm+Rpath.T@dRm
        
        s1, y1, w1 = Rpsi.T@(X-F.X)

        #############################################################
        #############################################################

        ks = 0.7
        ds = (Rpsi@Vr)[0]+ks*s1
        self.ds=ds

        ds1, dy1,dw1 = Rtheta@Vr-ds*np.array([1-F.C*y1, F.C*s1,0])

        psi_a=1.3
        y10,k1,k2,k3,k4,k5=1.25,1.5,1.8,0.09,3,1


        e=np.array([s1,y1,w1])
        de=np.array([ds1,dy1,dw1])

        cross_e=np.cross(e,np.array([1,0,0]))
        dcross_e=np.cross(de,np.array([1,0,0]))

        delta=-psi_a*tanh(cross_e)
        ddelta=-psi_a*(1-tanh(cross_e)**2)*dcross_e
        Rdelta=expm(self.adj(delta))
        dRdelta=self.adj(ddelta)@Rdelta

        epsi=logm(Rdelta@Rpsi.T)
        Kpsi=1
        dRpsi=(-Kpsi*Rdelta.T@Rpsi@epsi-Rdelta@dRdelta@Rpsi.T).T

        
        nu_d=1
        dnu=k1*(nu_d-nu)

        dRs=Rtheta.T@(dRpsi-dRtheta@Rs)
        dVr=dRs@np.array([nu,0,0])+Rs@np.array([dnu,0,0])
        print(dVr)

        w=np.flip(self.state[6:9])
        wd=k3*np.tanh(dVr/k5)
        D=np.array([[0,-1,0],[1,0,0],[0,0,0]])
        wd=D@wd
        u=k4*(wd-w)
        return u


if __name__ == '__main__':
    try:
        C=PFController()
    except rospy.ROSInterruptException:
        pass