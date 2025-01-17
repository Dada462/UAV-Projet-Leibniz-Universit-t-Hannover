import rospy
import pyqtgraph as pg
import numpy as np
import sys
from datetime import datetime
import time
from numpy import pi
from pyqtgraph.Qt import QtCore, QtWidgets, QtGui
from PyQt5.QtGui import QPainter, QBrush, QPen
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLineEdit, QLabel
from PyQt5.QtCore import Qt
import pyqtgraph.opengl as gl
from scipy.spatial.transform import Rotation
from std_msgs.msg import String
from geometry_msgs.msg import TwistStamped, Vector3
pg.setConfigOptions(antialias=True)


class RobotMesh():
    def __init__(self, size=np.eye(3)):
        verts = np.array([
            [0, 0, 0],
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 0],
            [0, 1, 1],
            [0, 0, 1],
            [1, 0, 1],
            [1, 1, 1]
        ])
        faces = np.array([
            [0, 1, 2],
            [2, 3, 0],
            [3, 4, 5],
            [5, 0, 3],
            [0, 1, 6],
            [5, 6, 0],
            [1, 2, 7],
            [7, 6, 1],
            [7, 4, 3],
            [3, 2, 7],
            [4, 5, 6],
            [6, 7, 4]
        ])
        vcenter = np.sum(verts, axis=0)/len(verts)
        verts = verts-vcenter
        verts = verts@size
        colors = np.array([
            [1, 0, 0, 1],
            [1, 0, 0, 1],
            [0, 0, 0, 1],
            [0, 0, 0, 1],
            [0, 1, 0, 1],
            [0, 1, 0, 1],
            [0.5, 0.5, 1, 1],
            [0.5, 0.5, 1, 1],
            [0, 1, 0, 1],
            [0, 1, 0, 1],
            [1, 0, 0, 1],
            [1, 0, 0, 1],
        ])
        self.base_vertices = verts
        self.vertices = verts
        self.center = vcenter
        self.position = np.zeros(3)
        self.colors = colors
        self.faces = faces

    def rotate(self, seq='XYZ', angles=[0, 0, 0], deg=False):
        r = Rotation.from_euler(seq=seq, angles=angles,
                                degrees=deg).as_matrix()
        self.vertices = self.base_vertices@r.T


class GLViewWidget_Modified(gl.GLViewWidget):
    def __init__(self, parent=None, devicePixelRatio=None, rotationMethod='euler'):
        super().__init__(parent, devicePixelRatio, rotationMethod)
        # self.pressed_keys = set()
        # self.keyboard = [0, 0, 0, 0, 0, 0]
        self.key_ids = [Qt.Key_Z, Qt.Key_S, Qt.Key_Q,
                        Qt.Key_D, Qt.Key_A, Qt.Key_E, Qt.Key_F, Qt.Key_G]
        self.keyboard = np.zeros(len(self.key_ids))

    def evalKeyState(self):
        pass

    # def keyPressEvent(self, event):
    #     self.pressed_keys.add(event.key())
    #     key_ids = [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left,
    #                Qt.Key_Right, Qt.Key_G, Qt.Key_H]
    #     keys = {key_ids[i]: i for i in range(len(key_ids))}
    #     for k in self.pressed_keys:
    #         if k in keys:
    #             self.keyboard[keys[k]] = 1
    #         if k == Qt.Key_Return or k == Qt.Key_Enter:
    #             self.clickMethod()
    #             self.update_values()

    # def keyReleaseEvent(self, event):
    #     self.pressed_keys.discard(event.key())
    #     key_ids = [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left,
    #                Qt.Key_Right, Qt.Key_G, Qt.Key_H]
    #     keys = {key_ids[i]: i for i in range(len(key_ids))}
    #     if event.key() in keys:
    #         self.keyboard[keys[event.key()]] = 0


class plot2D(QtWidgets.QMainWindow):
    def __init__(self, PF_controller=None, *args, **kwargs):
        super(plot2D, self).__init__(*args, **kwargs)

        self.graphWidget = pg.GraphicsLayoutWidget()
        self.graphWidget.setBackground('w')
        self.setCentralWidget(self.graphWidget)
        self.resize(650, 550)
        self.setWindowTitle('Plot Window')

        # Buttons
        reset_data = QPushButton(self.graphWidget)

        reset_data.setText('Reset data')

        reset_data.setGeometry(QtCore.QRect(0, 0, 100, 25))

        reset_data.clicked.connect(self.reset_data)

        # Test data
        self.positions = np.zeros((10**4, 6))
        self.positions_times = np.zeros(10**4)-1
        self.pos_counter = 0
        self.state = None
        self.pfc = PF_controller

        # Creating the widgets
        self.p = self.graphWidget.addPlot(col=0, row=0)
        self.data_plot = {0: pg.PlotCurveItem(
            pen=({'color': '#f12828', 'width': 3}), skipFiniteCheck=True, name='main')}
        self.N = 3000
        self.values = {0: np.zeros((self.N, 2))}
        self.cursors = {0: 0}
        self.p.addItem(self.data_plot[0])

        # Setting the plot
        # self.p.setLabel('left', 'y', **{'color': 'r', 'font-size': '20px'})
        self.p.setLabel('bottom', 't (s)', **
                        {'color': 'r', 'font-size': '20px'})
        self.p.addLegend()
        self.p.showGrid(x=True, y=True)
        self.p.setTitle("Plot", color="k", size="20px")

        self.i = 0
        self.timer = QtCore.QTimer()
        self.timer.setInterval(75)
        self.timer.timeout.connect(self.update_plot_data)
        self.timer.start()
        self.show()

    def plot(self, x, y, id=0, color='navy'):
        if not id in self.data_plot:
            if id == 1:
                print('hi')
                self.data_plot[id] = pg.PlotCurveItem(
                    pen=({'color': '#186ff6', 'width': 3}), skipFiniteCheck=True, name=str(id))
            elif id == 2:
                self.data_plot[id] = pg.PlotCurveItem(
                    pen=({'color': '#3df618', 'width': 3}), skipFiniteCheck=True, name=str(id))
                print('hi 2')
            else:
                self.data_plot[id] = pg.PlotCurveItem(
                    pen=({'color': color, 'width': 3}), skipFiniteCheck=True, name=str(id))
            self.p.addItem(self.data_plot[id])
            self.values[id] = np.zeros((self.N, 2))
            self.cursors[id] = 0
        if type(x) == np.float64 or type(x) == float or type(y) == np.float64 or type(y) == float:
            self.values[id][self.cursors[id]] = x, y
            self.cursors[id] += 1
        else:
            self.data_plot[id].setData(x=x, y=y)
        self.cursors[id] = self.cursors[id] % self.N

    def reset_data(self):
        for id in self.data_plot:
            self.values[id] = np.zeros((self.N, 2))
            self.cursors[id] = 0

    def update_plot_data(self):
        for id in self.data_plot:
            values = self.values[id][:self.cursors[id]]
            self.data_plot[id].setData(x=values[:, 0], y=values[:, 1])
        self.i += 1


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, PF_controller=None, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.w = GLViewWidget_Modified()
        self.setCentralWidget(self.w)
        self.resize(850, 750)
        self.move(500, 150)
        self.setWindowTitle('Mission Displayer')

        self.w.setBackgroundColor('w')
        self.w.setCameraPosition(distance=20)
        axis = gl.GLAxisItem(glOptions='opaque')
        axis.setSize(15, 15, 15)
        gx = gl.GLGridItem(color=(0, 0, 0, 40))
        gx.setSize(100, 100)
        gx.setSpacing(1, 1)
        self.w.addItem(gx)
        self.w.addItem(axis)

        # self.vehicle_mesh = RobotMesh(np.diag([0.6, 0.6, 0.35]))
        self.vehicle_mesh = RobotMesh(0.25*np.eye(3))
        self.vehicle = gl.GLMeshItem(vertexes=self.vehicle_mesh.vertices,
                                     faces=self.vehicle_mesh.faces, faceColors=self.vehicle_mesh.colors, smooth=False)
        self.w.addItem(self.vehicle)

        # Buttons
        hover = QPushButton(self)
        start_mission = QPushButton(self)
        stop_mission = QPushButton(self)
        reset_mission = QPushButton(self)
        keyboard_mode = QPushButton(self)
        land_button = QPushButton(self)
        waypoint_button = QPushButton(self)
        OA_button = QPushButton(self)

        start_mission.setText('Follow Path')
        stop_mission.setText('Home')
        hover.setText('Hover')
        reset_mission.setText('Reset Data')
        keyboard_mode.setText('KeyB')
        land_button.setText('Land')
        OA_button.setText('OA')

        start_mission.setGeometry(QtCore.QRect(0, 0, 100, 25))
        stop_mission.setGeometry(QtCore.QRect(105, 0, 100, 25))
        hover.setGeometry(QtCore.QRect(205, 0, 100, 25))
        reset_mission.setGeometry(QtCore.QRect(305, 0, 100, 25))
        land_button.setGeometry(QtCore.QRect(405, 0, 100, 25))
        keyboard_mode.setGeometry(QtCore.QRect(505, 0, 100, 25))
        waypoint_button.setGeometry(QtCore.QRect(605, 0, 100, 25))
        OA_button.setGeometry(QtCore.QRect(705, 0, 100, 25))

        start_mission.clicked.connect(self.start_recording_mission)
        stop_mission.clicked.connect(self.stop_recording_mission)
        hover.clicked.connect(self.hover_pub)
        reset_mission.clicked.connect(self.reset_mission_data)
        keyboard_mode.clicked.connect(self.keyboard_pub)
        land_button.clicked.connect(self.land_pub)
        waypoint_button.clicked.connect(self.waypoint_pub)
        OA_button.clicked.connect(self.OA_pub)

        self.robot_info_label_1 = QLabel(self)
        self.robot_info_label_1.setText('')
        self.robot_info_label_1.setFixedSize(100, 100)
        self.robot_info_label_1.move(10, 650)

        self.mission_state = {'start': False,
                              'go_home': True, 'keyboard': False}

        # Test data
        self.positions = np.zeros((10**4, 12))
        self.positions_times = np.zeros(10**4)-1
        self.pos_counter = 0
        self.state = None
        self.pfc = PF_controller
        self.path_points = np.zeros((1, 3))
        self.oa_path_points = np.zeros((1, 3))
        self.i = 0

        # Position trace
        self.trace = gl.GLLinePlotItem(
            color='#f12828', width=2, antialias=True)
        self.trace.setGLOptions('opaque')
        self.w.addItem(self.trace)

        if __name__ != '__main__':
            self.commands_sender = rospy.Publisher(
                '/pf_controller/user_input', String, queue_size=10)
            self.speed_pub = rospy.Publisher(
                '/mavros/setpoint_velocity/cmd_vel', TwistStamped, queue_size=10)
            # Path
            self.path = gl.GLLinePlotItem(
                color='#3486F4', width=3, antialias=True)
            self.oa_path = gl.GLLinePlotItem(
                color='#f3a60b', width=3, antialias=True)
            self.point_to_follow = gl.GLScatterPlotItem(
                size=0.25, color=(52/255, 244/255, 76/255, 1), pxMode=False)
            self.velodyne = gl.GLScatterPlotItem(
                size=0.05, color=(243/255, 25/255, 11/255, 0.5), pxMode=False)
            self.text_A=gl.GLTextItem(color='red',text='A')
            self.text_vel=gl.GLTextItem(color='red',text='')
            
            self.path.setGLOptions('opaque')
            self.oa_path.setGLOptions('opaque')
            self.velodyne.setGLOptions('opaque')
            self.point_to_follow.setGLOptions('translucent')

            self.w.addItem(self.path)
            self.w.addItem(self.oa_path)
            self.w.addItem(self.point_to_follow)
            self.w.addItem(self.velodyne)
            self.w.addItem(self.text_A)
            self.w.addItem(self.text_vel)
        else:
            # Path
            self.point_to_follow = gl.GLScatterPlotItem(
                pos=2*np.ones(3), size=0.1, color=(52/255, 244/255, 76/255, 1), pxMode=False)
            self.point_to_follow.setGLOptions('translucent')
            self.w.addItem(self.point_to_follow)

        # params = ['νpath', 'k0', 'k1','Kpath','ν','c1','amax'] # V4
        params = ['T', 'zmin', 'zmax', 'k0', 'k1']  # Thrust test
        try:
            default_values = list(np.load('params.npy'))
        except:
            default_values = list(np.zeros_like(params))
        if len(default_values) != len(params):
            default_values = np.zeros(len(params))
        self.nb_of_params = len(params)
        self.params = params
        self.values = default_values
        self.create_params_boxes()

        self.key_ids = [Qt.Key_Z, Qt.Key_S, Qt.Key_Q,
                        Qt.Key_D, Qt.Key_A, Qt.Key_E, 56, 53]
        self.keyboard = np.zeros(len(self.key_ids))
        self.pressed_keys = set()
        self.timer = QtCore.QTimer()
        self.timer.setInterval(75)
        self.timer.timeout.connect(self.update_plot_data)
        self.timer.start()

        self.s1_arrow = gl.GLLinePlotItem(
            width=3, color=(0, 0, 1, 0.8), glOptions='opaque')
        self.y1_arrow = gl.GLLinePlotItem(
            width=3, color=(0, 1, 0, 0.8), glOptions='opaque')
        self.w1_arrow = gl.GLLinePlotItem(
            width=3, color=(1, 0.5, 0.5, 0.8), glOptions='opaque')

        self.w.addItem(self.s1_arrow)
        self.w.addItem(self.y1_arrow)
        self.w.addItem(self.w1_arrow)
        self.show()

    def create_params_boxes(self):
        self.buttons_add = {}
        self.buttons_sub = {}
        self.textBoxes = {}
        self.labels = {}
        b_off = [0, 300]
        textSize = 40

        for i in range(self.nb_of_params):
            self.buttons_add[i] = QPushButton(self)
            self.buttons_add[i].setText('+')
            self.buttons_add[i].setGeometry(QtCore.QRect(
                25+textSize+b_off[0], 100+25*i+b_off[1], 25, 25))
            self.buttons_add[i].clicked.connect(self.click_function(True, i))
            self.buttons_sub[i] = QPushButton(self)
            self.buttons_sub[i].setText('-')
            self.buttons_sub[i].setGeometry(QtCore.QRect(
                50+textSize+b_off[0], 100+25*i+b_off[1], 25, 25))
            self.buttons_sub[i].clicked.connect(self.click_function(False, i))

            self.labels[i] = QLabel(self)
            self.labels[i].setStyleSheet(
                "background-color: lightgreen; border: 1px solid black;")
            self.labels[i].setText(self.params[i])
            self.labels[i].setGeometry(QtCore.QRect(
                0+b_off[0], 100+25*i+b_off[1], 25, 25))

            self.textBoxes[i] = QLineEdit(self)
            self.textBoxes[i].setText(str(self.values[i]))
            self.textBoxes[i].setGeometry(QtCore.QRect(
                25+b_off[0], 100+25*i+b_off[1], textSize, 25))

    def click_function(self, add, id):
        def click_method():
            if add:
                self.values[id] = self.values[id]+0.1
            else:
                self.values[id] = self.values[id]-0.1
            self.textBoxes[id].setText(str(np.round(self.values[id], 2)))
        return click_method

    def keyPressEvent(self, event):
        self.pressed_keys.add(event.key())
        key_ids = self.key_ids
        keys = {key_ids[i]: i for i in range(len(key_ids))}
        for k in self.pressed_keys:
            # self.keyboard=[k==Qt.Key_Z,k==Qt.Key_S,k==Qt.Key_Q,k==Qt.Key_D,k==Qt.Key_E,k==Qt.Key_A]
            if k in keys:
                self.keyboard[keys[k]] = 1
            if k == Qt.Key_Return or k == Qt.Key_Enter:
                self.update_values()

    def keyReleaseEvent(self, event):
        self.pressed_keys.discard(event.key())
        # key_ids = [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left,Qt.Key_Right, Qt.Key_G, Qt.Key_H]
        key_ids = self.key_ids
        keys = {key_ids[i]: i for i in range(len(key_ids))}
        if event.key() in keys:
            self.keyboard[keys[event.key()]] = 0

    def update_values(self):
        for i in range(self.nb_of_params):
            v = float(self.textBoxes[i].text())
            try:
                self.values[i] = v
            except:
                pass
        np.save('params.npy', self.values)
        print('Parameters enter: ', self.values)

    def update_plot_data(self):
        if self.state is not None:
            try:
                speed = np.linalg.norm(self.state[3:6])
                self.robot_info_label_1.setText('x={x:0.2f} m\ny={y:0.2f} m\nz={z:0.2f} m\ne={error:0.2f} cm\nv={speed:0.2f} m/s'.format(
                    x=self.state[0], y=self.state[1], z=self.state[2], error=self.error, speed=speed))
            except:
                speed = np.linalg.norm(self.state[3:6])
                self.robot_info_label_1.setText('x={x:0.2f}\ny={y:0.2f}\nz={z:0.2f}\n\nv={speed:0.2f} m/s'.format(
                    x=self.state[0], y=self.state[1], z=self.state[2], speed=speed))

            self.vehicle.setMeshData(vertexes=self.vehicle_mesh.vertices +
                                     self.state[:3], faces=self.vehicle_mesh.faces, faceColors=self.vehicle_mesh.colors)
            self.trace.setData(pos=self.positions[:self.pos_counter, :3])
            self.path.setData(pos=self.path_points)
            self.oa_path.setData(pos=self.oa_path_points)
            
            # OA & velodyne
            self.text_A.setData(pos=self.oa_path_points[0])
            closest_vel_point=self.closest_vel_point
            d=np.round(self.closest_vel_point_distance,2)
            self.s1_arrow.setData(pos=np.vstack((self.state[:3],closest_vel_point)))
            self.text_vel.setData(pos=(self.state[:3]+closest_vel_point)/2,text=str(d))
            
            self.point_to_follow.setData(pos=self.s_pos)
            self.velodyne.setData(pos=self.vel)
            self.i += 1
            self.keyboard = self.w.keyboard

            if self.mission_state['keyboard']:
                u = self.keyboard
                u = np.array([[1, -1, 0, 0, 0, 0, 0, 0],
                              [0, 0, 1, -1, 0, 0, 0, 0],
                              [0, 0, 0, 0, 0, 0, 1, -1],
                              [0, 0, 0, 0, 1, -1, 0, 0]])@u
                msg = TwistStamped()
                Rm = Rotation.from_euler('XYZ', self.state[6:9], degrees=False)
                u[:3] = Rm.apply(u[:3])
                dz = 1.5*(0.6-self.state[2])-1*self.state[5]
                msg.twist.linear = Vector3(*1*u[:2], dz)
                msg.twist.angular = Vector3(0, 0, 3.5*u[3])
                self.speed_pub.publish(msg)

    def start_recording_mission(self):
        # Reinitialize the data
        self.commands_sender.publish(String('FOLLOWPATH'))
        print('Mission started')
        self.mission_state['start'] = True
        self.mission_state['keyboard'] = False
        # self.pfc.calculate_metrics(self.positions)

    def stop_recording_mission(self):
        # Stop recording and save the data
        print('Mission is over')
        self.commands_sender.publish(String('HOME'))

        # self.mission_results()
        now = datetime.now()
        dt_string = now.strftime("%d.%m.%Y_%H.%M.%S")
        # print(self.positions_times.shape,self.positions.shape)
        # positions=np.hstack((self.positions,self.positions_times.reshape((-1,1))))

        # np.save('results/positions_'+dt_string+'.npy',positions)
        # np.save('results/path_to_follow_'+dt_string+'.npy',self.pfc.path_to_follow.X)

        self.mission_state['start'] = False
        self.mission_state['keyboard'] = False

    def keyboard_pub(self):
        self.mission_state['keyboard'] = True
        self.commands_sender.publish(String('KEYBOARD'))

    def hover_pub(self):
        self.mission_state['keyboard'] = False
        self.commands_sender.publish(String('HOVER'))

    def land_pub(self):
        self.mission_state['keyboard'] = False
        self.commands_sender.publish(String('LAND'))

    def waypoint_pub(self):
        self.mission_state['keyboard'] = False
        self.commands_sender.publish(String('WAYPOINT'))

    def OA_pub(self):
        self.mission_state['keyboard'] = True
        self.commands_sender.publish(String('OA'))

    def reset_mission_data(self):
        # self.pfc.s = 0
        self.positions = self.positions*0
        # self.pfc.PID.I=0
        self.pos_counter = 0
        self.data_to_plotx = []
        self.data_to_ploty1 = []
        self.data_to_ploty2 = []
        self.data_to_ploty3 = []

    def update_state(self, state, s_pos, error, vel,closest_point,closest_distance):
        self.state = state
        self.s_pos = s_pos
        self.vel = vel
        self.positions[self.pos_counter] = state
        self.positions_times[self.pos_counter] = time.time()
        self.vehicle_mesh.position = state[:3]
        self.vehicle_mesh.rotate('XYZ', state[6:9])
        self.pos_counter = (self.pos_counter+1) % (10**4)
        self.error = error
        self.closest_vel_point=closest_point
        self.closest_vel_point_distance=closest_distance

    def sawtooth(self, x):
        return (x+pi) % (2*pi)-pi   # or equivalently 2*arctan(tan(x/2))

    def mission_results(self):
        print('calculating results')


if __name__ == '__main__':
    ################################## Pyqt ##################################
    app = QtWidgets.QApplication(sys.argv)
    main = plot2D()
    T = np.linspace(-10, 10, 500)
    main.plot(T, 0.1*T**2, 0)
    # main.plot(T,np.sin(T),1)
    T = np.linspace(0, 10, 500)
    for t in T:
        main.plot(t, np.sin(t), 2)
    sys.exit(app.exec_())
    ################################## Pyqt ##################################
