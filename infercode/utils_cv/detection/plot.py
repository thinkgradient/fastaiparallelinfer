# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""
Helper module for visualizations
"""
import os
from pathlib import Path
from typing import List, Union, Tuple, Callable, Any, Iterator, Optional
from pathlib import Path

import numpy as np
import PIL
from PIL import Image, ImageDraw
from torch.utils.data import Subset
import matplotlib.pyplot as plt

from .bbox import _Bbox, AnnotationBbox, DetectionBbox
from .model import ims_eval_detections
from .references.coco_eval import CocoEvaluator
from ..common.misc import get_font
from .mask import binarise_mask, colorise_binary_mask, transparentise_mask


class PlotSettings:
    """ Simple class to contain bounding box params. """

    def __init__(
        self,
        rect_th: int = 4,
        rect_color: Tuple[int, int, int] = (255, 0, 0),
        text_size: int = 25,
        text_color: Tuple[int, int, int] = (255, 255, 255),
        mask_color: Tuple[int, int, int] = (2, 166, 101),
        mask_alpha: float = 0.5,
    ):
        self.rect_th = rect_th
        self.rect_color = rect_color
        self.text_size = text_size
        self.text_color = text_color
        self.mask_color = mask_color
        self.mask_alpha = mask_alpha


def plot_boxes(
    im: PIL.Image.Image,
    bboxes: List[_Bbox],
    title: str = None,
    plot_settings: PlotSettings = PlotSettings(),
) -> PIL.Image.Image:
    """ Plot boxes on Image and return the Image

    Args:
        im: The image to plot boxes on
        bboxes: a list of bboxes (either DetectionBbox or AnnotationBbox)
        title: optional title str to pass in to draw on the top of the image
        plot_settings: the parameter of the bounding boxes

    Returns:
        The same image with boxes and labels plotted on it
    """
    if len(bboxes) > 0:
        draw = ImageDraw.Draw(im)
        font = get_font(size=plot_settings.text_size)

        for bbox in bboxes:
            # do not draw background bounding boxes
            if bbox.label_idx == 0:
                continue

            box = [(bbox.left, bbox.top), (bbox.right, bbox.bottom)]

            # draw rect
            draw.rectangle(
                box,
                outline=plot_settings.rect_color,
                width=plot_settings.rect_th,
            )

            # write prediction class
            draw.text(
                (bbox.left, bbox.top),
                bbox.label_name,
                font=font,
                fill=plot_settings.text_color,
            )

        if title is not None:
            draw.text((0, 0), title, font=font, fill=plot_settings.text_color)

    return im


def plot_mask(
    im: Union[str, Path, PIL.Image.Image],
    mask: Union[str, Path, np.ndarray],
    plot_settings: PlotSettings = PlotSettings(),
) -> PIL.Image.Image:
    """ Put mask onto image.

    Assume the mask is already binary masks of [N, Height, Width], or
    grayscale mask of [Height, Width] with different values
    representing different objects, 0 as background.
    """
    if isinstance(im, (str, Path)):
        im = Image.open(im)

    # convert to RGBA for transparentising
    im = im.convert('RGBA')
    # colorise masks
    binary_masks = binarise_mask(mask)
    colored_masks = [
        colorise_binary_mask(bmask, plot_settings.mask_color) for bmask in
        binary_masks
    ]
    # merge masks into img one by one
    for cmask in colored_masks:
        tmask = Image.fromarray(
            transparentise_mask(cmask, plot_settings.mask_alpha)
        )
        im = Image.alpha_composite(im, tmask)

    return im


def display_bboxes_mask(
    bboxes: List[_Bbox],
    im_path: Union[Path, str],
    mask_path: Union[Path, str] = None,
    ax: Optional[plt.axes] = None,
    plot_settings: PlotSettings = PlotSettings(),
    figsize: Tuple[int, int] = (12, 12),
) -> None:
    """ Draw image with bounding boxes and mask.

    Args:
        bboxes: A list of _Bbox, could be DetectionBbox or AnnotationBbox
        im_path: the location of image path to draw
        mask_path: the location of mask path to draw
        ax: an optional ax to specify where you wish the figure to be drawn on
        plot_settings: plotting parameters
        figsize: figure size

    Returns nothing, but plots the image with bounding boxes, labels and masks
    if any.
    """
    # Read image
    im = Image.open(im_path)

    # set an image title
    title = os.path.basename(im_path)

    if mask_path is not None:
        # plot masks on im
        im = plot_mask(im_path, mask_path)

    if bboxes is not None:
        # plot boxes on im
        im = plot_boxes(im, bboxes, title=title, plot_settings=plot_settings)

    # display the image
    if ax is not None:
        ax.set_xticks([])
        ax.set_yticks([])
        ax.imshow(im)
    else:
        plt.figure(figsize=figsize)
        plt.imshow(im)
        plt.xticks([])
        plt.yticks([])
        plt.show()


def plot_grid(
    plot_func: Callable[..., None],
    args: Union[Callable, Iterator, Any],
    rows: int = 1,
    cols: int = 3,
    figsize: Tuple[int, int] = (16, 16),
) -> None:
    """ Helper function to plot image grids.

    Args:
        plot_func: callback to call on each subplot. It should take an 'ax' as
        the last param.
        args: args can be passed in in many forms. It can be an iterator, a
        callable, or simply some static parameters. If it is an iterator, this
        function will call `next` on it each time. If it is a callable, this
        function will call the function and use the returned values each time.
        rows: rows to plot
        cols: cols to plot, default is 3. NOTE: use cols=3 for best looking
        grid
        figsize: figure size (will be dynamically modified in the code

    Returns nothing but plots graph
    """
    fig_height = rows * 8
    figsize = (figsize[0], fig_height)

    fig, axes = plt.subplots(rows, cols, figsize=figsize)

    if rows == 1 or cols == 1:
        axes = [axes]

    for row in axes:
        for ax in row:
            # dynamic injection of params into callable
            arguments = (
                args()
                if isinstance(args, Callable)
                else (next(args) if hasattr(args, "__iter__") else args)
            )
            try:
                plot_func(arguments, ax)
            except Exception:
                plot_func(*arguments, ax)

    plt.subplots_adjust(top=0.8, bottom=0.2, hspace=0.1, wspace=0.2)


def plot_detection_vs_ground_truth(
    im_path: str,
    det_bboxes: List[DetectionBbox],
    anno_bboxes: List[AnnotationBbox],
    ax: plt.axes,
) -> None:
    """ Plots bounding boxes of ground_truths and detections.

    Args:
        im_path: the image to plot
        det_bboxes: a list of detected annotations
        anno_bboxes: a list of ground_truth detections
        ax: the axis to plot on

    Returns nothing, but displays a graph
    """
    im = Image.open(im_path).convert("RGB")

    # plot detections
    det_params = PlotSettings(rect_color=(255, 0, 0), text_size=1)
    im = plot_boxes(
        im,
        det_bboxes,
        title=os.path.basename(im_path),
        plot_settings=det_params,
    )

    # plot ground truth boxes
    anno_params = PlotSettings(rect_color=(0, 255, 0), text_size=1)
    im = plot_boxes(
        im,
        anno_bboxes,
        title=os.path.basename(im_path),
        plot_settings=anno_params,
    )

    # show image
    ax.set_xticks([])
    ax.set_yticks([])
    ax.imshow(im)


# ===== Precision - Recall curve =====


def _setup_pr_axes(ax: plt.axes, title: str) -> plt.axes:
    """ Setup the plot settings for plotting PR curves. """
    ax.set_xlabel("recall", fontsize=12)
    ax.set_ylabel("precision", fontsize=12)
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0, 1.01)
    ax.set_title(title, fontsize=14)
    ax.grid(True)
    return ax


def _get_precision_recall_settings(
    iou_thrs: Union[int, slice],
    rec_thrs: Union[int, slice] = slice(0, None),
    cat_ids: int = slice(0, None),
    area_rng: int = 0,
    max_dets: int = 2,
) -> Tuple[Union[int, slice], Union[int, slice], int, int, int]:
    """ Returns the indices or slices needed to index into the
    coco_eval.eval['precision'] object.

    coco_eval.eval['precision'] is a 5-dimensional array. Each dimension
    represents the following:
    1. [T] 10 evenly distributed thresholds for IoU, from 0.5 to 0.95.
    2. [R] 101 recall thresholds, from 0 to 101
    3. [K] label, set to slice(0, None) to get precision over all the labels in
    the dataset. Then take the mean over all labels.
    4. [A] area size range of the target (all-0, small-1, medium-2, large-3)
    5. [M] The maximum number of detection frames in a single image where index
    0 represents max_det=1, 1 represents max_det=10, 2 represents max_det=100

    Therefore, coco_eval.eval['precision'][0, :, 0, 0, 2] represents the value
    of 101 precisions corresponding to 101 recalls from 0 to 100 when IoU=0.5.

    Args:
        iou_thrs: the IoU thresholds to return
        rec_thrs: the recall thresholds to return
        cat_ids: label ids to use for evaluation
        area_rng: object area ranges for evaluation
        max_dets: thresholds on max detections per image

    Return the settings as a tuple to be passed into:
    `coco_eval.eval['precision']`
    """
    return iou_thrs, rec_thrs, cat_ids, area_rng, max_dets


def _plot_pr_curve_iou_range(
    ax: plt.axes,
    coco_eval: CocoEvaluator,
    iou_type: Optional[str] = None,
) -> None:
    """ Plots the PR curve over varying iou thresholds averaging over [K]
    categories. """
    x = np.arange(0.0, 1.01, 0.01)
    iou_thrs_idx = range(0, 10)
    iou_thrs = np.linspace(
        0.5, 0.95, np.round((0.95 - 0.5) / 0.05) + 1, endpoint=True
    )

    # get_cmap() - a function that maps each index in 0, 1, ..., n-1 to a distinct
    # RGB color; the keyword argument name must be a standard mpl colormap name.
    cmap = plt.cm.get_cmap("hsv", len(iou_thrs))

    ax = _setup_pr_axes(
        ax, f"Precision-Recall Curve ({iou_type}) @ different IoU Thresholds"
    )
    for i, c in zip(iou_thrs_idx, iou_thrs):
        arr = coco_eval.eval["precision"][_get_precision_recall_settings(i)]
        arr = np.average(arr, axis=1)
        ax.plot(x, arr, c=cmap(i), label=f"IOU={round(c, 2)}")

    ax.legend(loc="lower left")


def _plot_pr_curve_iou_mean(
    ax: plt.axes,
    coco_eval: CocoEvaluator,
    iou_type: Optional[str] = None,
) -> None:
    """ Plots the PR curve, averaging over iou thresholds and [K] labels. """
    x = np.arange(0.0, 1.01, 0.01)
    ax = _setup_pr_axes(
        ax, f"Precision-Recall Curve ({iou_type}) - Mean over IoU Thresholds"
    )
    avg_arr = np.mean(  # mean over K labels
        np.mean(  # mean over iou thresholds
            coco_eval.eval["precision"][
                _get_precision_recall_settings(slice(0, None))
            ],
            axis=0,
        ),
        axis=1,
    )

    ax.plot(x, avg_arr, c="black", label=f"IOU=mean")
    ax.legend(loc="lower left")


def plot_pr_curves(
    evaluator: CocoEvaluator, figsize: Tuple[int, int] = (16, 8)
) -> None:
    """ Plots two graphs to illustrate the Precision Recall.

    This method uses the CocoEvaluator object from the references provided by
    pytorch, which in turn uses the COCOEval from pycocotools.

    source: https://github.com/cocodataset/cocoapi/blob/master/PythonAPI/pycocotools/cocoeval.py

    Args:
        evaluator: CocoEvaluator to get evaluation results from
        figsize: the figsize to plot the two graphs across

    Raises:
        Exception if accumulate hasn't been called on the passed in
        CocoEvaluator

    Returns nothing, but plots PR graphs.
    """
    coco_eval = evaluator.coco_eval["bbox"]
    if not coco_eval.eval:
        raise Exception(
            "`accumulate()` has not been called on the passed in coco_eval object."
        )

    nrows = len(evaluator.coco_eval)
    fig, axes = plt.subplots(nrows, 2, figsize=figsize)
    for i, (k, coco_eval) in enumerate(evaluator.coco_eval.items()):
        _plot_pr_curve_iou_range(
            axes[i, 0] if nrows > 1 else axes[0], coco_eval, k
        )
        _plot_pr_curve_iou_mean(
            axes[i, 1] if nrows > 1 else axes[1], coco_eval, k
        )

    plt.show()




# ===== Correct/missing detection counts curve =====


def _plot_counts_curves_im(
    ax: plt.axes,
    score_thresholds: List[float],
    im_error_counts: List[int],
    im_wrong_det_counts: List[int],
    im_missed_gt_counts: List[int],
    im_neg_det_counts: List[int],
) -> None:
    """ Plot image-level correct/incorrect counts vs score thresholds """
    if im_neg_det_counts:
        ax.plot(
            score_thresholds,
            im_neg_det_counts,
            "y",
            label="Negative images with detections",
        )
    ax.plot(
        score_thresholds,
        im_error_counts,
        "r",
        label="Images with missed gt or wrong detections",
    )
    ax.plot(
        score_thresholds,
        im_wrong_det_counts,
        "g:",
        label="Images with wrong detections",
    )
    ax.plot(
        score_thresholds,
        im_missed_gt_counts,
        "b:",
        label="Images with missed ground truth",
    )

    ax.legend()
    ax.set_xlabel("Score threshold")
    ax.set_ylabel("Frequency")
    ax.set_title("Image counts", fontsize=14)
    ax.grid(True)


def _plot_counts_curves_obj(
    ax: plt.axes,
    score_thresholds: List[float],
    obj_missed_gt_counts: List[int],
    obj_wrong_det_counts: List[int],
    obj_neg_det_counts: List[int],
) -> None:
    """ Plot object-level correct/incorrect counts vs score thresholds """
    if obj_neg_det_counts:
        ax.plot(
            score_thresholds,
            obj_neg_det_counts,
            "y",
            label="Total number of detections within negative images",
        )
    ax.plot(
        score_thresholds,
        obj_wrong_det_counts,
        "g:",
        label="Total number of wrong detections",
    )
    ax.plot(
        score_thresholds,
        obj_missed_gt_counts,
        "b:",
        label="Total number of missed ground truths",
    )


    ax.legend()
    ax.set_xlabel("Score threshold")
    ax.set_ylabel("Frequency")
    ax.set_title("Object counts", fontsize=14)
    ax.grid(True)


def plot_counts_curves(
    detections: List[List[DetectionBbox]],
    data_ds: Subset,
    detections_neg: List[List[DetectionBbox]] = None,
    figsize: Tuple[int, int] = (16, 8),
) -> None:
    """ Plot object-level and image-level correct/incorrect counts vs score thresholds

    Args:
        detections: Detector prediction output for all test images
        data_ds: Test dataset, used to extract ground truth bboxes
        detections_neg: Detector prediction output for all negative images
        figsize: the figsize to plot the two graphs across

    Returns nothing, but plots count graphs.
    """
    # compute image and object level counts
    (
        score_thresholds,
        im_error_counts,
        im_wrong_det_counts,
        im_missed_gt_counts,
        obj_wrong_det_counts,
        obj_missed_gt_counts,
        im_neg_det_counts,
        obj_neg_det_counts,
    ) = ims_eval_detections(detections, data_ds, detections_neg)

    # plot
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)
    _plot_counts_curves_im(
        ax1,
        score_thresholds,
        im_error_counts,
        im_wrong_det_counts,
        im_missed_gt_counts,
        im_neg_det_counts,
    )
    _plot_counts_curves_obj(
        ax2,
        score_thresholds,
        obj_missed_gt_counts,
        obj_wrong_det_counts,
        obj_neg_det_counts,
    )
    plt.show()
