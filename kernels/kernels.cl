#define E .0000001f

__kernel void matrix_dot_vector(__global const float4 *matrix,
__global const float4 *vector, __global float *result)
{
    int gid = get_global_id(0);
    result[gid] = dot(matrix[gid], vector[0]);
}

__kernel void square_sum(__global float *template, __global float *frame, __global float *output)
{
    int gid = get_global_id(0);
    output[gid] = pow((template[gid] - frame[gid]),2);
}

__kernel void init_labels(__global float *after_mask, __global float *labels)
{
    //int label = 1;
    //int gid = get_global_id(0);
    //if (after_mask[gid] > 40){
    //    labels[gid] = label;
    //}
}

__kernel void rgb2hsv(read_only image2d_t src, write_only image2d_t dest){
    const sampler_t sampler =  CLK_NORMALIZED_COORDS_FALSE | CLK_ADDRESS_CLAMP_TO_EDGE | CLK_FILTER_NEAREST;
    int2 pos = (int2)(get_global_id(0), get_global_id(1));
    uint4 pix = read_imageui(src, sampler, pos);
    // A simple test operation: delete pixel in form of a checkerboard pattern
    float x = (float)pix.x/255;
    float y = (float)pix.y/255;
    float z = (float)pix.z/255;

    float cmax = fmax(x,y);
    cmax = fmax(cmax, z);
    float cmin = fmin(x,y);
    cmin = fmin(cmin, z);
    float diff = cmax-cmin;

    float v = cmax;
    float h = 0;
    float s = 0;

    if (cmin == cmax)
        h = 0;
    else if (cmax == x)
        h = (unsigned int)( 0 + 43 * (y - z) / diff);
    else if (cmax == y)
        h = (unsigned int)(85 + 43 * (z - x) / diff);
    else if (cmax == z)
        h = (unsigned int)(171 + 43 * (x - y) / diff);

    if (cmax == 0)
        s = 0;
    else
        s = (float)(diff/cmax);

    pix.x = (int)(h);
    pix.y = (int)(s*255);
    pix.z = (int)(v*255);
    write_imageui(dest, pos, pix);
}

__kernel void hsvMask(read_only image2d_t src, __global const float4 *matrix, write_only image2d_t dest){
    const sampler_t sampler =  CLK_NORMALIZED_COORDS_FALSE | CLK_ADDRESS_CLAMP_TO_EDGE | CLK_FILTER_NEAREST;
    int2 pos = (int2)(get_global_id(0), get_global_id(1));
    uint4 pix = read_imageui(src, sampler, pos);

    /*
    if(pix.x<=matrix[0][0] || pix.x >= matrix[1][0]){
        pix.x = 0;
        pix.y = 0;
        pix.z = 0;
    }
    if(pix.y<=matrix[0][1] || pix.y >= matrix[1][1]){
        pix.y = 0;
    }
    if(pix.z<=matrix[0][2] || pix.z >= matrix[1][2]){
        pix.z = 0;
    }

    */
}