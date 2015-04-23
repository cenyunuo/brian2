'''
An example that uses a function from external C library (OpenCV in this case).
Works for all C-based code generation targets (i.e. for weave,
Cython and the cpp_standalone device) but not for numpy.
'''
import os
import urllib2
import cv2  # Import OpenCV2
import cv2.cv as cv  # Import the cv subpackage, needed for some constants

from brian2 import *

defaultclock.dt = 1*ms
prefs.codegen.target = 'weave'
prefs.logging.std_redirection = False
set_device('cpp_standalone')
filename = 'Megamind.avi'

if not os.path.exists(filename):
    print 'Trying to download the video file'
    response = urllib2.urlopen('http://docs.opencv.org/_downloads/Megamind.avi')
    data = response.read()
    with open(filename, 'wb') as f:
        f.write(data)

video = cv2.VideoCapture(filename)
width, height, frame_count = (int(video.get(cv.CV_CAP_PROP_FRAME_WIDTH)),
                              int(video.get(cv.CV_CAP_PROP_FRAME_HEIGHT)),
                              int(video.get(cv.CV_CAP_PROP_FRAME_COUNT)))
fps = 24
time_between_frames = 1*second/fps
print 'fps', fps, 'time between frames:', time_between_frames

prefs.codegen.cpp.libraries += ['opencv_highgui']
prefs.codegen.cpp.headers += ['<opencv2/core/core.hpp>', '<opencv2/highgui/highgui.hpp>']
@implementation('cpp', '''
double* get_frame(bool new_frame)
{
    static cv::VideoCapture source("%FILENAME%");
    static cv::Mat frame;
    static double* grayscale_frame = (double*)malloc(%WIDTH%*%HEIGHT%*sizeof(double));
    if (new_frame)
    {
        source >> frame;
        double mean_value = 0;
        for (int row=0; row<%HEIGHT%; row++)
            for (int col=0; col<%WIDTH%; col++)
            {
                const double grayscale_value = (frame.at<cv::Vec3b>(row, col)[0] +
                                                frame.at<cv::Vec3b>(row, col)[1] +
                                                frame.at<cv::Vec3b>(row, col)[2])/(3.0*128);
                mean_value += grayscale_value / (%WIDTH% * %HEIGHT%);
                grayscale_frame[row*%WIDTH% + col] = grayscale_value;
            }
        // subtract the mean
        for (int i=0; i<%HEIGHT%*%WIDTH%; i++)
            grayscale_frame[i] -= mean_value;
    }
    return grayscale_frame;
}

double video_input(const int x, const int y)
{
    // Get the current frame (or a new frame in case we are asked for the first
    // element
    double *frame = get_frame(x==0 && y==0);
    return frame[y*%WIDTH% + x];
}
'''.replace('%FILENAME%', filename).replace('%WIDTH%', str(width)).replace('%HEIGHT%', str(height)))
@check_units(x=1, y=1, result=1)
def video_input(x, y):
    # we assume this will only be called in the custom operation (and not for
    # example in a reset or synaptic statement), so we don't need to do indexing
    # but we can directly return the full result
    _, frame = video.read()
    grayscale = frame.mean(axis=2)
    grayscale /= 128.  # scale everything between 0 and 2
    return grayscale.ravel() - grayscale.ravel().mean()


N = width * height
tau, tau_th = 10*ms, time_between_frames
G = NeuronGroup(N, '''dv/dt = (-v + I)/tau : 1
                      dv_th/dt = -v_th/tau_th : 1
                      row : integer
                      column : integer
                      I : 1   # input current''',
                threshold='v>v_th', reset='v=0; v_th = 2*v_th + 0.5')
G.row = 'i/width'
G.column = 'i%width'

update_input = G.custom_operation('I = video_input(column, row)',
                                  dt=time_between_frames)
mon = SpikeMonitor(G)
state_mon = StateMonitor(G, ['v', 'v_th'], record=0)
runtime = 1000*ms # 0.25*frame_count*time_between_frames
run(runtime, report='text')
device.build(compile=True, run=True)
# plt.scatter(G.column[::7], G.row[::7], c=G.v[::7],
#             edgecolor='none', cmap='gray')
# plt.gca().invert_yaxis()
# plt.figure()
# plt.plot(state_mon.t/ms, state_mon[0].v)
# plt.plot(state_mon.t/ms, state_mon[0].v_th)
# print state_mon[0].v_th[:]
# plt.show()

# Avoid going through the whole Brian2 indexing machinery too much
i, t, row, column = mon.i[:], mon.t[:], G.row[:], G.column[:]

import matplotlib.animation as animation

# TODO: Use overlapping windows
stepsize = 100*ms
def next_spikes():
    step = next_spikes.step
    if step*stepsize > runtime:
        next_spikes.step=0
        raise StopIteration()
    spikes = i[(t>=step*stepsize) & (t<(step+1)*stepsize)]
    next_spikes.step += 1
    yield column[spikes], row[spikes]
next_spikes.step = 0

fig, ax = plt.subplots()
dots, = ax.plot([], [], 'k.', markersize=2, alpha=.25)
ax.set_xlim(0, width)
ax.set_ylim(0, height)
ax.invert_yaxis()
def run(data):
    x, y = data
    dots.set_data(x, y)

    # Clear the old dots
    #return old_dots,

ani = animation.FuncAnimation(fig, run, next_spikes, blit=False, repeat=True,
                              repeat_delay=1000)
plt.show()
