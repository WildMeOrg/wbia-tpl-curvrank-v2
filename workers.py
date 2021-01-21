# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
from wbia_curvrank_v2 import dorsal_utils
import annoy
import cv2
import numpy as np

# import fluke_utils
import wbia_curvrank_v2.functional as F
from tqdm import tqdm
import matplotlib

matplotlib.use('Agg')  # NOQA
import matplotlib.pyplot as plt
import six

if six.PY2:
    import cPickle as pickle
else:
    import pickle


def preprocess_images_star(fpath_side, height, width, output_targets):
    return preprocess_images(
        *fpath_side, height=height, width=width, output_targets=output_targets
    )


def preprocess_images(fpath, side, height, width, output_targets):
    resz_target = output_targets[fpath]['resized']
    trns_target = output_targets[fpath]['transform']
    mask_target = output_targets[fpath]['mask']

    img = cv2.imread(fpath)
    # mirror images marked as "Right" to simulate a left-view
    flip = side.lower() == 'right'
    resz, mask, M = F.preprocess_image(img, flip, height, width)

    _, resz_buf = cv2.imencode('.png', resz)
    _, mask_buf = cv2.imencode('.png', mask)

    with resz_target.open('wb') as f1, trns_target.open('wb') as f2, mask_target.open(
        'wb'
    ) as f3:
        f1.write(resz_buf)
        pickle.dump(M, f2, pickle.HIGHEST_PROTOCOL)
        f3.write(mask_buf)


def localization_identity(fpath, height, width, input_targets, output_targets):
    img_path = input_targets[fpath]['resized'].path
    msk_path = input_targets[fpath]['mask'].path
    img = cv2.imread(img_path)
    msk = cv2.imread(msk_path)
    loc_lr_target = output_targets[fpath]['localization']
    trns_target = output_targets[fpath]['transform']
    mask_target = output_targets[fpath]['mask']
    lclz_trns = np.eye(3, dtype=np.float32)

    _, img_loc_lr_buf = cv2.imencode('.png', img)
    _, msk_loc_lr_buf = cv2.imencode('.png', msk)

    with loc_lr_target.open('wb') as f1, trns_target.open('wb') as f2, mask_target.open(
        'wb'
    ) as f3:
        f1.write(img_loc_lr_buf)
        pickle.dump(lclz_trns, f2, pickle.HIGHEST_PROTOCOL)
        f3.write(msk_loc_lr_buf)


# to_process: [fpath1, fpath2, ...] (for batching to gpu)
def localization_stn(
    to_process, batch_size, height, width, func, input_targets, output_targets
):
    num_batches = (len(to_process) + batch_size - 1) // batch_size
    # logger.info('%d batches of size %d to process' % (
    #    num_batches, self.batch_size))
    for i in tqdm(range(num_batches), total=num_batches, leave=False):
        idx_range = range(i * batch_size, min((i + 1) * batch_size, len(to_process)))
        fpaths_batch, imgs_batch, masks_batch = [], [], []
        for i, idx in enumerate(idx_range):
            fpath = to_process[idx]

            img_path = input_targets[fpath]['resized'].path
            img = cv2.imread(img_path)

            msk_path = input_targets[fpath]['mask'].path
            msk = cv2.imread(msk_path)

            fpaths_batch.append(fpath)
            imgs_batch.append(img)
            masks_batch.append(msk)

        localized, masks, transforms = F.localize(
            imgs_batch, masks_batch, height, width, func
        )
        for i, fpath in enumerate(fpaths_batch):
            loc_lr_target = output_targets[fpath]['localization']
            trns_target = output_targets[fpath]['transform']
            mask_target = output_targets[fpath]['mask']

            img = localized[i]
            msk = masks[i]
            trns = transforms[i]

            _, img_buf = cv2.imencode('.png', img)
            _, msk_buf = cv2.imencode('.png', msk)

            with loc_lr_target.open('wb') as f1, trns_target.open(
                'wb'
            ) as f2, mask_target.open('wb') as f3:
                f1.write(img_buf)
                pickle.dump(trns, f2, pickle.HIGHEST_PROTOCOL)
                f3.write(msk_buf)


def refine_localization_star(
    fpath_side, scale, height, width, input1_targets, input2_targets, output_targets
):
    return refine_localization(
        *fpath_side,
        scale=scale,
        height=height,
        width=width,
        input1_targets=input1_targets,
        input2_targets=input2_targets,
        output_targets=output_targets
    )


# input1_targets: preprocess_images_targets
# input2_targets: localization_targets
def refine_localization(
    fpath, side, scale, height, width, input1_targets, input2_targets, output_targets
):
    tpath = input1_targets[fpath]['transform'].path
    with open(tpath, 'rb') as f:
        pre_transform = pickle.load(f, encoding='latin1')
    lpath = input2_targets[fpath]['transform'].path
    with open(lpath, 'rb') as f:
        loc_transform = pickle.load(f, encoding='latin1')

    img_orig = cv2.imread(fpath)
    flip = side.lower() == 'right'

    img_refn, msk_refn = F.refine_localization(
        img_orig, flip, pre_transform, loc_transform, scale, height, width
    )

    loc_hr_target = output_targets[fpath]['refn']
    mask_target = output_targets[fpath]['mask']

    _, img_loc_hr_buf = cv2.imencode('.png', img_refn)
    _, msk_loc_hr_buf = cv2.imencode('.png', msk_refn)
    with loc_hr_target.open('wb') as f1, mask_target.open('wb') as f2:
        f1.write(img_loc_hr_buf)
        f2.write(msk_loc_hr_buf)


# input1_targets: localization_targets
# input2_targets: segmentation_targets
def find_keypoints(fpath, method, input1_targets, input2_targets, output_targets):
    coords_target = output_targets[fpath]['keypoints-coords']
    visual_target = output_targets[fpath]['keypoints-visual']

    loc_fpath = input1_targets[fpath]['localization'].path
    msk_fpath = input1_targets[fpath]['mask'].path
    loc = cv2.imread(loc_fpath)
    msk = cv2.imread(msk_fpath, cv2.IMREAD_GRAYSCALE)

    seg_fpath = input2_targets[fpath]['segmentation-data'].path
    with open(seg_fpath, 'rb') as f:
        seg = pickle.load(f, encoding='latin1')

    # start, end = fluke_utils.find_keypoints(rsp)
    start, end = F.find_keypoints(method, seg, msk)

    # TODO: what to write for failed extractions?
    if start is not None:
        cv2.circle(loc, tuple(start[::-1]), 3, (255, 0, 0), -1)
    if end is not None:
        cv2.circle(loc, tuple(end[::-1]), 3, (0, 0, 255), -1)
    _, visual_buf = cv2.imencode('.png', loc)
    with coords_target.open('wb') as f1, visual_target.open('wb') as f2:
        pickle.dump((start, end), f1, pickle.HIGHEST_PROTOCOL)
        f2.write(visual_buf)


# input1_targets: refinement_targets
# input2_targets: segmentation_targets
# input3_targets: keypoints_targets
def extract_outline(
    fpath,
    scale,
    allow_diagonal,
    cost_func,
    input1_targets,
    input2_targets,
    input3_targets,
    output_targets,
):
    coords_target = output_targets[fpath]['outline-coords']
    visual_target = output_targets[fpath]['outline-visual']

    rfn_fpath = input1_targets[fpath]['refn'].path
    msk_fpath = input1_targets[fpath]['mask'].path
    rfn = cv2.imread(rfn_fpath)
    msk = cv2.imread(msk_fpath)

    seg_fpath = input2_targets[fpath]['segmentation-full-data']
    key_fpath = input3_targets[fpath]['keypoints-coords']
    with seg_fpath.open('rb') as f1, key_fpath.open('rb') as f2:
        segm = pickle.load(f1, encoding='latin1')
        (start, end) = pickle.load(f2, encoding='latin1')

    if start is not None and end is not None:
        outline = F.extract_outline(
            rfn, msk, segm, scale, start, end, cost_func, allow_diagonal
        )
    else:
        outline = np.array([])

    # TODO: what to write for failed extractions?
    if outline.shape[0] > 0:
        rfn[outline[:, 0], outline[:, 1]] = (255, 0, 0)
        rfn[outline[0, 0], outline[0, 1]] = (0, 0, 255)
        rfn[outline[-1, 0], outline[-1, 1]] = (0, 0, 255)

    _, visual_buf = cv2.imencode('.png', rfn)
    with coords_target.open('wb') as f1, visual_target.open('wb') as f2:
        pickle.dump(outline, f1, pickle.HIGHEST_PROTOCOL)
        f2.write(visual_buf)


# input1_targets: refinement_targets
# input2_targets: extract_outline_targets
def separate_edges(fpath, method, input1_targets, input2_targets, output_targets):
    refinement_target = input1_targets[fpath]['refn']
    outline_coords_target = input2_targets[fpath]['outline-coords']

    rfn = cv2.imread(refinement_target.path)
    with open(outline_coords_target.path, 'rb') as f:
        outline = pickle.load(f, encoding='latin1')

    # Two failure cases are possible:
    # (1) No outline exists, so no separation is possible.
    # (2) The separation of the edges fails.
    if outline.shape[0] > 0:
        if method is None:
            leading_edge, trailing_edge = outline[:0], outline[0:]
        else:
            leading_edge, trailing_edge = F.separate_edges(method, outline)
        if leading_edge is not None and trailing_edge is not None:
            rfn[leading_edge[:, 0], leading_edge[:, 1]] = (255, 0, 0)
            rfn[trailing_edge[:, 0], trailing_edge[:, 1]] = (0, 0, 255)
    else:
        leading_edge, trailing_edge = None, None

    vis_target = output_targets[fpath]['visual']
    _, rfn_buf = cv2.imencode('.png', rfn)

    with vis_target.open('wb') as f1:
        f1.write(rfn_buf)

    leading_target = output_targets[fpath]['leading-coords']
    trailing_target = output_targets[fpath]['trailing-coords']
    with leading_target.open('wb') as f1, trailing_target.open('wb') as f2:
        pickle.dump(leading_edge, f1, pickle.HIGHEST_PROTOCOL)
        pickle.dump(trailing_edge, f2, pickle.HIGHEST_PROTOCOL)


def compute_curvature_star(fpath_scales, transpose_dims, input_targets, output_targets):
    return compute_curvature(
        *fpath_scales,
        transpose_dims=transpose_dims,
        input_targets=input_targets,
        output_targets=output_targets
    )


# input_targets: extract_high_resolution_outline_targets
def compute_curvature(fpath, scales, transpose_dims, input_targets, output_targets):
    trailing_coords_target = input_targets[fpath]['trailing-coords']
    with open(trailing_coords_target.path, 'rb') as f:
        trailing_edge = pickle.load(f, encoding='latin1')

    scales = np.array(scales)
    if trailing_edge is not None:
        curv = F.compute_curvature(trailing_edge, scales)
        assert not np.isnan(curv).any(), 'nan in curvature for %s' % (fpath)
    # write the failures too or it seems like the task did not complete
    else:
        curv = None

    curv_target = output_targets[fpath]['curvature']
    with curv_target.open('a') as h5f:
        # store each scale (column) of the curvature matrix separately
        for j, scale in enumerate(scales):
            if curv is not None:
                h5f.create_dataset('%.3f' % scale, data=curv[:, j])
            else:
                h5f.create_dataset('%.3f' % scale, data=None, dtype=np.float32)


def compute_gauss_descriptors_star(
    fpath_scales,
    num_keypoints,
    feat_dim,
    contour_length,
    uniform,
    input_targets,
    output_targets,
):
    return compute_gauss_descriptors(
        *fpath_scales,
        num_keypoints=num_keypoints,
        feat_dim=feat_dim,
        contour_length=contour_length,
        uniform=uniform,
        input_targets=input_targets,
        output_targets=output_targets
    )


def compute_gauss_descriptors(
    fpath,
    scales,
    num_keypoints,
    feat_dim,
    contour_length,
    uniform,
    input_targets,
    output_targets,
):
    trailing_coords_target = input_targets[fpath]['trailing-coords']
    with open(trailing_coords_target.path, 'rb') as f:
        trailing_edge = pickle.load(f, encoding='latin1')

    descriptors = []
    if trailing_edge is not None:
        trailing_edge = trailing_edge[:, ::-1]
        for (m, s) in scales:
            desc = dorsal_utils.diff_of_gauss_descriptor(
                trailing_edge, m, s, num_keypoints, feat_dim, contour_length, uniform,
            )
            descriptors.append(desc.astype(np.float32))
    else:
        descriptors = None

    desc_target = output_targets[fpath]['descriptors']
    # write the failures too or it seems like the task did not complete
    with desc_target.open('a') as h5f:
        for i, s in enumerate(scales):
            if descriptors is not None:
                h5f.create_dataset('%s' % (s,), data=descriptors[i])
            else:
                h5f.create_dataset('%s' % (s,), data=None, dtype=np.float32)


def compute_curv_descriptors_star(
    fpath_scales,
    num_keypoints,
    feat_dim,
    curv_length,
    uniform,
    input_targets,
    output_targets,
):
    return compute_curv_descriptors(
        *fpath_scales,
        num_keypoints=num_keypoints,
        fdim=feat_dim,
        curv_length=curv_length,
        uniform=uniform,
        input_targets=input_targets,
        output_targets=output_targets
    )


def compute_curv_descriptors(
    fpath,
    scales,
    num_keypoints,
    fdim,
    curv_length,
    uniform,
    input_targets,
    output_targets,
):
    block_curv_target = input_targets[fpath]['curvature']
    with block_curv_target.open('r') as h5f:
        shapes = [h5f['%.3f' % s].shape for s in scales]
        curv = None if None in shapes else np.vstack(h5f['%.3f' % s][:] for s in scales).T

    desc_target = output_targets[fpath]['descriptors']
    with desc_target.open('a') as h5f:
        if curv is not None:
            feat_mats = F.compute_curv_descriptors()
            for sidx, scale in enumerate(scales):
                descriptors = feat_mats[sidx]
                h5f.create_dataset('%.3f' % scale, data=descriptors)
        # create dummy data at each scale
        else:
            for sidx, scale in enumerate(scales):
                h5f.create_dataset('%.3f' % scale, data=None, dtype=np.float32)


def visualize_individuals(fpath, input_targets, output_targets):
    separate_edges_target = input_targets[fpath]['visual']
    img = cv2.imread(separate_edges_target.path)

    visualization_target = output_targets[fpath]['image']
    _, img_buf = cv2.imencode('.png', img)
    with visualization_target.open('wb') as f:
        f.write(img_buf)


def identify_encounter_descriptors_star(
    qind_qenc,
    db_names,
    scales,
    k,
    qr_fpath_dict,
    db_fpath_dict,
    input1_targets,
    input2_targets,
    output_targets,
):
    return identify_encounter_descriptors(
        *qind_qenc,
        db_names=db_names,
        scales=scales,
        k=k,
        qr_fpath_dict=qr_fpath_dict,
        db_fpath_dict=db_fpath_dict,
        input1_targets=input1_targets,
        input2_targets=input2_targets,
        output_targets=output_targets
    )


def build_annoy_index_star(data_fpath):
    return build_annoy_index(*data_fpath)


def build_annoy_index(data, fpath):
    f = data.shape[1]  # feature dimension
    index = annoy.AnnoyIndex(f, metric='euclidean')
    for i, _ in enumerate(data):
        index.add_item(i, data[i])
    index.build(10)
    index.save(fpath)


def identify_encounter_descriptors(
    qind,
    qenc,
    db_names,
    scales,
    k,
    qr_fpath_dict,
    db_fpath_dict,
    input1_targets,
    input2_targets,
    output_targets,
):
    descriptors_dict = {s: [] for s in scales}
    # load the descriptors from all images in this encounter
    for fpath in qr_fpath_dict[qind][qenc]:
        target = input1_targets[fpath]['descriptors']
        descriptors = dorsal_utils.load_descriptors_from_h5py(target, scales)
        for s in scales:
            descriptors_dict[s].append(descriptors[s])

    db_indivs = db_fpath_dict.keys()
    aggr_scores = {dind: 0.0 for dind in db_indivs}
    for s in descriptors_dict:
        names = db_names[s]
        index_fpath = input2_targets[s]
        scores = F.lnbnn_identify(index_fpath, k, descriptors_dict[s], names)
        for name in db_indivs:
            aggr_scores[name] += scores[name]

    with output_targets[qind][qenc].open('wb') as f:
        pickle.dump(scores, f, pickle.HIGHEST_PROTOCOL)


def identify_encounter_star(
    qind_qenc, qr_curv_dict, db_curv_dict, simfunc, output_targets
):
    return identify_encounter(
        *qind_qenc,
        qr_curv_dict=qr_curv_dict,
        db_curv_dict=db_curv_dict,
        simfunc=simfunc,
        output_targets=output_targets
    )


def identify_encounter(qind, qenc, qr_curv_dict, db_curv_dict, simfunc, output_targets):
    dindivs = db_curv_dict.keys()
    qcurvs = qr_curv_dict[qind][qenc]
    scores = F.dtwsw_identify(qcurvs, db_curv_dict, dindivs, simfunc)

    with output_targets[qind][qenc].open('wb') as f:
        pickle.dump(scores, f, pickle.HIGHEST_PROTOCOL)


# input1_targets: evaluation_targets (the result dicts)
# input2_targets: edges_targets (the separate_edges visualizations)
# input3_targets: block_curv_targets (the curvature vectors)
def visualize_misidentifications(
    qind,
    qr_dict,
    db_dict,
    num_db,
    num_qr,
    scales,
    curv_length,
    input1_targets,
    input2_targets,
    input3_targets,
    output_targets,
):
    dindivs = np.hstack(db_dict.keys())  # TODO: add sorted() everywhere
    qencs = input1_targets[qind].keys()
    for qenc in qencs:
        with input1_targets[qind][qenc].open('rb') as f:
            result_dict = pickle.load(f, encoding='latin1')
        result_across_db = np.hstack([result_dict[dind] for dind in dindivs])
        indivs_across_db = np.hstack(
            [np.repeat(dind, len(db_dict[dind])) for dind in dindivs]
        )
        db_fnames = np.hstack([db_dict[dind] for dind in dindivs])
        query_fnames = np.hstack(qr_dict[qind][qenc])

        assert db_fnames.shape[0] == result_across_db.shape[1]
        best_score_per_query = result_across_db.min(axis=1)
        qr_best_idx = best_score_per_query.argsort(axis=0)[0:num_qr]
        qr_best_fnames = query_fnames[qr_best_idx]
        qr_best_scores = result_across_db[qr_best_idx]

        db_best_idx = qr_best_scores.argsort(axis=1)

        db_best_fnames = db_fnames[db_best_idx[:, 0:num_db]]
        db_best_scores = np.array(
            [qr_best_scores[i, db_best_idx[i]] for i in np.arange(db_best_idx.shape[0])]
        )
        db_best_indivs = indivs_across_db[db_best_idx]

        db_best_qr_idx = np.argmax(db_best_indivs == qind, axis=1)
        db_best_qr_fnames = db_fnames[db_best_idx][
            np.arange(db_best_qr_idx.shape[0]), db_best_qr_idx
        ]

        db_best_qr_indivs = db_best_indivs[
            np.arange(db_best_idx.shape[0]), db_best_qr_idx
        ]

        db_best_qr_scores = db_best_scores[
            np.arange(db_best_qr_idx.shape[0]), db_best_qr_idx
        ]

        f, axarr = plt.subplots(
            2 + min(db_best_fnames.shape[1], num_db),  # rows
            min(qr_best_fnames.shape[0], num_qr),  # cols
            figsize=(22.0, 12.0),
        )
        if axarr.ndim == 1:
            axarr = np.expand_dims(axarr, axis=1)  # ensure 2d
        db_rows = []
        for i, _ in enumerate(qr_best_fnames):
            qr_edge_fname = input2_targets[qr_best_fnames[i]]['visual']
            qr_curv_fname = input3_targets[qr_best_fnames[i]]['curvature']
            db_edge_fnames = [
                input2_targets[name]['visual'] for name in db_best_fnames[i]
            ]
            db_qr_edge_fname = input2_targets[db_best_qr_fnames[i]]['visual']
            db_qr_curv_fname = input3_targets[db_best_qr_fnames[i]]['curvature']

            db_curv_fnames = [
                input3_targets[name]['curvature'] for name in db_best_fnames[i]
            ]

            qr_img = cv2.resize(cv2.imread(qr_edge_fname.path), (256, 256))
            cv2.putText(
                qr_img,
                '%s: %s' % (qind, qenc),
                (10, qr_img.shape[0] - 10),
                cv2.FONT_HERSHEY_PLAIN,
                1.0,
                (0, 255, 0),
            )

            db_row = []
            for didx, db_edge_fname in enumerate(db_edge_fnames):
                db_img = cv2.resize(cv2.imread(db_edge_fname.path), (256, 256))
                dind = db_best_indivs[i, didx]
                dscore = db_best_scores[i, didx]
                cv2.putText(
                    db_img,
                    '%d) %s: %.6f' % (1 + didx, db_best_indivs[i, didx], dscore),
                    (10, db_img.shape[0] - 10),
                    cv2.FONT_HERSHEY_PLAIN,
                    1.0,
                    (0, 255, 0) if dind == qind else (0, 0, 255),
                )
                db_row.append(db_img)

            db_qr_img = cv2.resize(cv2.imread(db_qr_edge_fname.path), (256, 256),)
            cv2.putText(
                db_qr_img,
                '%d) %s: %.6f'
                % (1 + db_best_qr_idx[i], db_best_qr_indivs[i], db_best_qr_scores[i]),
                (10, db_qr_img.shape[0] - 10),
                cv2.FONT_HERSHEY_PLAIN,
                1.0,
                (0, 255, 0),
            )

            db_row = np.hstack(db_row)
            db_rows.append(np.hstack((qr_img, db_row, db_qr_img)))

            qcurv = dorsal_utils.load_curv_mat_from_h5py(
                qr_curv_fname, scales, curv_length, False
            )
            axarr[0, i].set_title('%s: %s' % (qind, qenc), size='xx-small')
            axarr[0, i].plot(np.arange(qcurv.shape[0]), qcurv)
            axarr[0, i].set_ylim((0, 1))
            axarr[0, i].set_xlim((0, qcurv.shape[0]))
            axarr[0, i].xaxis.set_visible(False)
            for didx, db_curv_fname in enumerate(db_curv_fnames, start=1):
                dcurv = dorsal_utils.load_curv_mat_from_h5py(
                    db_curv_fname, scales, curv_length, False
                )
                axarr[didx, i].plot(np.arange(dcurv.shape[0]), dcurv)
                axarr[didx, i].set_title(
                    '%d) %s: %.6f'
                    % (didx, db_best_indivs[i, didx - 1], db_best_scores[i, didx - 1]),
                    size='xx-small',
                )
                axarr[didx, i].set_ylim((0, 1))
                axarr[didx, i].set_xlim((0, dcurv.shape[0]))
                axarr[didx, i].xaxis.set_visible(False)

            db_qr_curv = dorsal_utils.load_curv_mat_from_h5py(
                db_qr_curv_fname, scales, curv_length, False
            )
            axarr[-1, i].plot(np.arange(db_qr_curv.shape[0]), db_qr_curv)
            axarr[-1, i].set_title(
                '%d) %s: %.6f'
                % (1 + db_best_qr_idx[i], db_best_qr_indivs[i], db_best_qr_scores[i]),
                size='xx-small',
            )
            axarr[-1, i].set_ylim((0, 1))
            axarr[-1, i].set_xlim((0, db_qr_curv.shape[0]))
            axarr[-1, i].xaxis.set_visible(False)

        grid = np.vstack(db_rows)

        _, edges_buf = cv2.imencode('.png', grid)
        with output_targets[qind][qenc]['separate-edges'].open('wb') as f:
            f.write(edges_buf)

        with output_targets[qind][qenc]['curvature'].open('wb') as f:
            plt.savefig(f, bbox_inches='tight')
        plt.clf()
        plt.close()
