import numpy as np
import cv2
import pyopencl as cl
import pyopencl.cltypes
import glob
import os, sys
import time

from sign import Sign
from GPUSetup import GPUSetup


class TrafficSignRecognition():
    def __init__(self):
        self.templates = []
        self.templates_hsv = []
        self.templates_mask = []
        self.template_preprocesing()


    def template_preprocesing(self):
        for filename in glob.iglob(os.getcwd() + '/templates/*.png', recursive=True):
            template = cv2.cvtColor(cv2.imread(filename), cv2.COLOR_RGB2RGBA)
            self.templates.append(template)

            h = template.shape[0]
            w = template.shape[1]

            # *Buffors
            template_buf = cl.image_from_array(GPUSetup.context, template, 4)
            fmt = cl.ImageFormat(cl.channel_order.RGBA, cl.channel_type.UNSIGNED_INT8)
            dest_buf = cl.Image(GPUSetup.context, cl.mem_flags.WRITE_ONLY, fmt, shape=(w, h))

            # *RGB to HSV
            GPUSetup.program.rgb2hsv(GPUSetup.queue, (w, h), None, template_buf, dest_buf)
            template_hsv = np.empty_like(template)
            cl.enqueue_copy(GPUSetup.queue, template_hsv, dest_buf, origin=(0, 0), region=(w, h))
            self.templates_hsv.append(template_hsv)

            # *Apply masks
            template_mask = self.clear_sign(template_hsv, template)
            self.templates_mask.append(template_mask)
    

    def clear_sign(self,img_hsv, img=None):
        h = img_hsv.shape[0]
        w = img_hsv.shape[1]
        cont_img_hsv = np.ascontiguousarray(img_hsv)

        red_mask = np.zeros((1, 2), cl.cltypes.float4)
        red_mask[0, 0] = (150, 70, 40, 0)  # Lower bound red
        red_mask[0, 1] = (210, 255, 255, 0)  # Upper bound red
        
        black_mask = np.zeros((1, 2), cl.cltypes.float4)
        black_mask[0, 0] = (0, 0, 0, 0)  # Lower bound black
        black_mask[0, 1] = (255, 255, 100, 0)  # Upper bound black

        #*Buffors
        fmt = cl.ImageFormat(cl.channel_order.RGBA, cl.channel_type.UNSIGNED_INT8)
        dest_buf = cl.Image(GPUSetup.context, cl.mem_flags.WRITE_ONLY, fmt, shape=(w, h))

        #*Red mask
        img_buf = cl.image_from_array(GPUSetup.context, cont_img_hsv, 4)
        mask_buf = cl.Buffer(GPUSetup.context, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR, hostbuf=red_mask)
        GPUSetup.program.hsv_bin_mask(GPUSetup.queue, (w, h), None, img_buf, mask_buf, dest_buf)
        img_mask_red = np.empty_like(cont_img_hsv)
        cl.enqueue_copy(GPUSetup.queue, img_mask_red, dest_buf, origin=(0, 0), region=(w, h))

        #*Black mask
        img_buf = cl.image_from_array(GPUSetup.context, cont_img_hsv, 4)
        mask_buf = cl.Buffer(GPUSetup.context, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR, hostbuf=black_mask)
        GPUSetup.program.hsv_bin_mask_center(GPUSetup.queue, (w, h), None, img_buf, mask_buf, np.int32(w), np.int32(h), dest_buf)
        img_mask_black = np.empty_like(cont_img_hsv)
        cl.enqueue_copy(GPUSetup.queue, img_mask_black, dest_buf, origin=(0, 0), region=(w, h))

        #*Merge both 
        img_buff_red = cl.image_from_array(GPUSetup.context, img_mask_red, 4)
        img_buff_black = cl.image_from_array(GPUSetup.context, img_mask_black, 4)
        GPUSetup.program.merge_bin(GPUSetup.queue, (w, h), None, img_buff_red, img_buff_black, dest_buf)
        img_merge = np.empty_like(cont_img_hsv)
        cl.enqueue_copy(GPUSetup.queue, img_merge, dest_buf, origin=(0, 0), region=(w, h))

        # # *-----------------------------DEBUG---------------------------------
        # img_concate_Verti = np.concatenate((img, img_hsv), axis=0)
        # img_gray = img_hsv[:,:,2]
        # blur = cv2.GaussianBlur(img_gray,(5,5),0)
        # _, img_otsu = cv2.threshold(img_gray,0,255,cv2.THRESH_BINARY| cv2.THRESH_OTSU)

        # cv2.imshow('Original and HSV', img_concate_Verti)
        # cv2.imshow('Gray', img_gray)
        # cv2.imshow("Otsu by cv", img_otsu)
        # cv2.imshow("Hsv", img_hsv)
        # cv2.imshow("After Red Mask",img_mask_red)
        # cv2.imshow("After Black Mask",img_mask_black)
        # cv2.imshow("Merge of masks", img_merge)

        # key = cv2.waitKey(10)
        # while (key != ord('w')):
        #     key = cv2.waitKey(19)
        #     pass
        # # *-------------------------------------------------------------------

        return img_merge


    def load_new_frame(self, frame):
        self.frame = cv2.cvtColor(frame, cv2.COLOR_RGB2RGBA)
        self.height, self.width, self.channels = frame.shape
        self.objects_coords = []
        self.signs = []


    def frame_preprocessing(self):
        # *Load and convert source image
        frame = np.array(self.frame)

        # *Set properties
        h = frame.shape[0]
        w = frame.shape[1]
        mask = np.zeros((1, 2), cl.cltypes.float4)
        mask[0, 0] = (165, 90, 70, 0)  # Lower bound
        mask[0, 1] = (195, 255, 255, 0)  # Upper bound

        # *Buffors
        frame_buf = cl.image_from_array(GPUSetup.context, frame, 4)
        fmt = cl.ImageFormat(cl.channel_order.RGBA, cl.channel_type.UNSIGNED_INT8)
        dest_buf = cl.Image(GPUSetup.context, cl.mem_flags.WRITE_ONLY, fmt, shape=(w, h))

        # *RGB to HSV
        GPUSetup.program.rgb2hsv(GPUSetup.queue, (w, h), None, frame_buf, dest_buf)
        self.hsv = np.empty_like(frame)
        cl.enqueue_copy(GPUSetup.queue, self.hsv, dest_buf, origin=(0, 0), region=(w, h))

        # *Apply mask
        frame_buf = cl.image_from_array(GPUSetup.context, self.hsv, 4)
        mask_buf = cl.Buffer(GPUSetup.context, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR, hostbuf=mask)
        GPUSetup.program.hsv_mask(GPUSetup.queue, (w, h), None, frame_buf, mask_buf, dest_buf)
        self.after_mask = np.empty_like(frame)
        cl.enqueue_copy(GPUSetup.queue, self.after_mask, dest_buf, origin=(0, 0), region=(w, h))

        return self.after_mask


    def frame_preprocessing_cv(self):
        self.hsv = cv2.cvtColor(self.frame, cv2.COLOR_BGR2HSV)
        # define range of blue color in HSV
        lower_blue = np.array([165, 120, 70])
        upper_blue = np.array([195, 255, 255])
        # Threshold the HSV image to get only blue colors
        mask = cv2.inRange(self.hsv, lower_blue, upper_blue)
        # Bitwise-AND mask and original image
        self.after_mask = cv2.bitwise_and(self.frame, self.frame, mask=mask)
        return self.after_mask


    def connected_components(self, offset=5, min_object_size=100, min_sign_area = 1000, red_pix_ratio = 0.5):
        self.frame_preprocessing()
        start_time_all = time.time()
        label = 1
        # Coordinates (indices [x, y]) of pixels with R channel (BGR code) greater than 40
        coords = np.argwhere(self.after_mask[:, :, 2] > 40)
        labels = np.zeros(shape=(self.height, self.width), dtype=int)

        # Assigning initial labels for pixels with specific coordinates
        for coord in coords:
            labels[coord[0], coord[1]] = label
            label += 1

        # Connecting pixels using kernels (8 connectivity)
        transitions = 0
        timer = 0;
        timer_kernel = 0;

        while True:
            try:
                start_time_kernel = time.time()
                mem_flags = cl.mem_flags
                # build input & destination labels array
                labels_cc_buf = cl.Buffer(GPUSetup.context,  mem_flags.READ_WRITE | mem_flags.COPY_HOST_PTR, size=labels.nbytes, hostbuf=labels)
                # execute OpenCL function
                GPUSetup.program.connected_components(GPUSetup.queue, labels.shape, None, labels_cc_buf)
                # copy result back to host
                labels_cc = np.empty_like(labels)
                cl.enqueue_copy(GPUSetup.queue, labels_cc, labels_cc_buf)
                elapsed_time_kernel = time.time() - start_time_kernel
                timer_kernel+=elapsed_time_kernel
                start_time = time.time()

                if((labels_cc==labels).all()):
                    elapsed_time = time.time() - start_time
                    timer+=elapsed_time
                    break
                else:
                    elapsed_time = time.time() - start_time
                    timer += elapsed_time
                    labels=labels_cc
                    transitions += 1
            except Exception as ex:
                print(ex)
        print("Elapsed time in kernels: ", timer_kernel)
        print("Elapsed time python: ", timer)
        print("Labels connected. Transitions: ", transitions)

        objects = np.unique(labels)
        objects = np.delete(objects, np.where(objects == 0))

        # Rejecting small objects
        for object in objects:
            if np.count_nonzero(labels == object) < min_object_size:
                labels[labels == object] = 0
                objects = np.delete(objects, np.where(objects == object))

        # Getting coords of objects
        for object in objects:
            most_left = self.width
            most_right = 0
            most_top = self.height
            most_bottom = 0
            for coord in coords:
                if labels[coord[0], coord[1]] == object:
                    if (coord[1] < most_left): most_left = coord[1]
                    if (coord[1] > most_right): most_right = coord[1]
                    if (coord[0] < most_top): most_top = coord[0]
                    if (coord[0] > most_bottom): most_bottom = coord[0]
            self.objects_coords.append([(most_left, most_top), (most_right, most_bottom)])

            area = (most_right - most_left) * (most_bottom-most_top)
            if np.count_nonzero(labels == object)/area < red_pix_ratio:
                if area > min_sign_area:                #Check size
                    sign = Sign(x=most_left, y=most_top, width=most_right - most_left, height=most_bottom - most_top)
                    self.signs.append(sign)

        #Drawing detected objects
        for sign in self.signs:
            cv2.rectangle(self.frame, (sign.x, sign.y), (sign.x+sign.width, sign.y+sign.height), (0, 255, 0), 2)

        #Printing objects data
        for key, sign in enumerate(self.signs):
            sign.print_info(key)

        for coord in coords:
            if labels[coord[0], coord[1]] > 0:
                self.after_mask[coord[0], coord[1]] = [255, 0, 0, 0]

        elapsed_time_all = time.time() - start_time_all
        print("Whole Sign Detection: ", elapsed_time_all)
        self.templateSumSquare()
        return self.frame


    def templateSumSquare(self):
        print("***********************\nTemplates num: ", len(self.templates))
        print("Signs num: ", len(self.signs))

        full_frame_img = self.hsv
        results = []

        start_time = time.time()
        for sign in self.signs:
            # Load sign + masking and binaryzation
            frame_img = full_frame_img[sign.y:sign.y+sign.height, sign.x:sign.x+sign.width]
            frame_masked =  np.array(self.clear_sign(frame_img)[:,:,2]).astype(np.float64)
            frame_masked_flat = frame_masked.flatten()

            single_sign_results = []
            for template in self.templates_mask:
                template_arr = cv2.resize(template, (sign.width, sign.height), interpolation=cv2.INTER_AREA)
                template_masked = np.array(template_arr[:,:,2]).astype(np.float64)
                template_masked_flat = template_masked.flatten()

                # # *-----------------------------DEBUG---------------------------------
                # cv2.imshow('TEMPLATE_MASK',template_masked)
                # cv2.imshow('FRAME_MASK',frame_masked)

                # key = cv2.waitKey(10)
                # while (key != ord('w')):
                #     key = cv2.waitKey(19)
                #     pass
                # # *-------------------------------------------------------------------

                #Calculate error/difference
                template_buf = cl.Buffer(GPUSetup.context, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR,hostbuf=template_masked_flat)
                frame_buf = cl.Buffer(GPUSetup.context, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR,hostbuf=frame_masked_flat)
                ssd_buf = cl.Buffer(GPUSetup.context, cl.mem_flags.WRITE_ONLY, template_masked_flat.nbytes)
                GPUSetup.program.square_sum(GPUSetup.queue, template_masked_flat.shape, None, template_buf, frame_buf, ssd_buf)

                # copy result back to host
                ssd = np.empty_like(template_masked_flat)
                cl.enqueue_copy(GPUSetup.queue, ssd, ssd_buf)
                single_sign_results.append(np.sum(ssd)/len(ssd))
                print(single_sign_results)

            results.append(np.argmin(single_sign_results))
            # if min(single_sign_results) < 8000:
            sign.type = np.argmin(single_sign_results)

            # *----------------------------DEBUG----------------------------------
            if sign.type is not None:
                print("\n++++++++++++++\nType: ", sign.type, " | X: ", sign.x, " | Y: ", sign.y, " | Width: ", sign.width,
                    " | Height: ", sign.height)
                print("Sum squared errors: ", single_sign_results)
            else:
                print("\n--------------\nType: ", sign.type, " | X: ", sign.x, " | Y: ", sign.y, " | Width: ", sign.width,
                    " | Height: ", sign.height)
                print("Sum squared errors: ", single_sign_results)
            # *-------------------------------------------------------------------
            break

        elapsed_time = time.time() - start_time
        print("Sign recognition time: ", elapsed_time)
        return results
