import numpy as np


def resize_to_multiple(images, multiples):
    '''Resize a batch of images in the height and width dimensions so their size are an integer
    multiple of some value.

    Parameters
    ----------
    images  :   tf.Tensor
                Tensor of shape [batch, height, width, channels]
    multiples   :   int or tuple
                    The value/s that should evenly divide the resized image's dimensions
    '''
    from tensorflow.image import resize_images
    _, h, w, _ = images.get_shape()
    # if only one multiple, assume it's the value to use for all dims
    if not isinstance(multiples, tuple):
        multiples = multiples * 2
    new_h, new_w = [int(ceil(input_shape[0] / multiples[0])),
                    int(ceil(input_shape[1] / multiples[1]))]
    return resize_images(images, [new_h, new_w])


def image_pairs(image_sequence, sequence_length):
    '''Generate sequences of stacked pairs of images where two 3-channel images are merged to on
    6-channel image. If the image sequence length is not evenly divided by the sequence length,
    fewer than the total number of images will be yielded.


    Parameters
    ----------
    image_sequence  :   np.ndarray
                        Array of shape (num, h, w, 3)
    sequence_length  :  int
                        Number of elements (6-channel imgs) yielded each time

    Returns
    -------
    np.ndarray
        Array of shape (sequence_length, h, w, 6)
    '''
    N, h, w, c = image_sequence.shape
    for idx in range(0, N, sequence_length):
        stacked_indices = np.empty((sequence_length - 1) * 2, dtype=np.uint8)
        batch_indices = np.arange(sequence_length - 1) + idx
        stacked_indices[0::2] = batch_indices
        stacked_indices[1::2] = batch_indices + 1
        # stacked is [img0, img1, img1, img2, img2, img3, ...]
        # stacked.shape = (sequence_length * 2, h, w, c)
        stacked = image_sequence[stacked_indices, ...]

        # return array stacks every 2 images together and thus has 6 channels per image, each image
        # appears twice
        ret = np.empty((sequence_length, h, w, 2 * c), dtype=stacked.dtype)

        indices = np.arange(0, sequence_length - 1)
        ret[indices, ..., 0:3] = stacked[indices * 2]
        ret[indices, ..., 3:6] = stacked[indices * 2 + 1]

        assert (ret[0, ..., :3] == image_sequence[0]).all()
        assert (ret[0, ..., 3:] == image_sequence[1]).all()

        yield ret


def subtract_mean_rgb(image_sequence):
    '''Subtract the rgb mean in-place. The mean is computed and subtracted on each channel. The mean
    is computed and subtracted on each channel.

    Parameters
    ----------
    image_sequence  :   np.ndarray
                        Array of shape (N, h, w, c)
    '''
    N, h, w, c = image_sequence.shape
    # compute mean separately for each channel
    mode = image_sequence.mean((0, 1, 2)).astype(image_sequence.dtype)
    np.subtract(image_sequence, mode, out=image_sequence)


def convert_large_array(file_in, file_out, dtype, factor=1.0):
    '''Convert data type of an array possibly too large to fit in memory.
    This uses memory-mapped files and will therefore be very slow.

    Parameters
    ----------
    file_in :   str
                Name of the input file
    file_out    :   str
                    Name of the output file
    dtype   :   np.dtype
                Destination data type
    factor  :   float
                Scaling factor to apply to all elements
    '''
    source = np.lib.format.open_memmap(file_in, mode='r')
    dest = np.lib.format.open_memmap(file_out, mode='w+', dtype=dtype, shape=source.shape)
    np.copyto(dest, source, casting='unsafe')
    if factor != 1.0:
        np.multiply(dest, factor, out=dest)


import conversions
import numpy as np

class DataManager(object):
    def __init__(self,
                 path_to_images='data/images.npy',
                 path_to_poses='data/poses.npy',
                 batch_size=100,
                 seq_len=2
                 ):
        self.poses      = np.load(path_to_poses)
        self.images     = np.load(path_to_images)
        self.seq_len    = seq_len
        self.batch_size = batch_size
        # additional frames needed depending on sequence length
        self.add_frames = self.seq_len - 1

        self.N = self.images.shape[0]
        self.H = self.images.shape[1]
        self.W = self.images.shape[2]
        self.C = self.images.shape[3]

        self.image_indices = np.arange(batch_size + self.add_frames)

        self.image_stack_batch = np.zeros(
            [self.batch_size, self.H, self.W, self.C * self.seq_len]
        )

    def getImageShape(self):
        return (self.H, self.W, self.C)

    def poseContainsQuaternion(self):
        return self.poses.shape[1] == 7

    def convertPosesToRPY(self):
        self.poses = conversions.posesFromQuaternionToRPY(self.poses)

    def batches(self):

        for batch_idx in range(0, self.N, len(self.image_indices)):
            # creating batch

            # TODO: better
            if batch_idx + len(self.image_indices) > self.N:
                break

            image_indices_global = self.image_indices + batch_idx

            # for seq_len = 3
            # image_indices_global[:-2], image_indices_global[1:-1], image_indices_global[2:]

            # build differences of poses
            # later pictures poses - first pictures poses
            diff_poses = self.poses[image_indices_global[self.add_frames:]] -self.poses[image_indices_global[:-self.add_frames] ]

            # build image sequences
            for idx in range(0, self.seq_len):
                begin = self.C * idx
                end = self.C * (idx + 1)
                if idx == self.seq_len - 1:
                    self.image_stack_batch[..., begin:end] = self.images[image_indices_global[idx:]]
                else:
                    self.image_stack_batch[..., begin:end] = self.images[image_indices_global[idx:-(self.add_frames - idx)]]

            yield self.image_stack_batch, diff_poses