#!/bin/python3
# dependency: numpy,scipy.stats, scipy.optimize,

import numpy as np
import pandas as pd
import multiprocessing as mp
from framework.utilities import sqrt_ginv
from itertools import product
from decimal import *
from scipy.stats import multivariate_normal as MVN

### Optimization of Variance Component Model for importance sampling process (Lightweight code) 
def LL_fun(x,n,P_sq,w):
    'Log Likelihood Function of PLEIO statistic'
    return(-0.5*(n*np.log(2*np.pi)+sum(np.log(w+x))+sum(P_sq/(w+x))));

def LLp_fun(x,P_sq,w):
    'Log Likelihood Function derivative to x'
    return(0.5*(sum(1/(w+x))-sum(P_sq/(w+x)**2)));

def LLdp_fun(x,P_sq, w):
    'Log Likelihood Function derivative to x^2'
    return(-0.5*(sum(1/(w+x)**2)-2*sum(P_sq/(w+x)**3)));

def NR_root(f, df, x, P_sq, w, i = 0, iter_max = 10000, tol = 2.22044604925e-16**0.5):
    'Newton Raphson Method implemented in PLEIO'
    while ( abs(f(x,P_sq,w)) > tol ):
        x = x - f(x,P_sq,w) / df(x,P_sq,w);
        i = i + 1;
        if (i == iter_max):
            break;
    return(x)

def vcm_optimization_IS (b, n, w, t_v , tol = 2.22044604925e-16**0.5):
    t = [10**(i/4) for i in range(-36,24,1)];
    crossP = t_v.dot(b);
    P_sq = crossP**2;
    init = t[np.argmax([LL_fun(i, n, P_sq, w) for i in t])];
    mle_tausq = NR_root(LLp_fun, LLdp_fun, init, P_sq, w);
    if (mle_tausq <0):
        mle_tausq = 0;
    null_ll = LL_fun(0, n, P_sq, w);
    alt_ll = LL_fun(mle_tausq, n, P_sq, w) ;
    if(alt_ll < null_ll):
        mle_tausq = 0;
        alt_ll = null_ll;
    return (- 2 * (null_ll - alt_ll))

### generate multi sampling distributions 
def generate_P(mean, factor, D, n):
    class Pj(object):
        '''
        Pj is a sampling density function of the deterministic importance sampling procedure 
        The class define the covariance matrix and means of Pj
        '''
        def __init__(self, means, cov):
            self.means = means;
            self.cov = cov;
            self.pdf = None;

    P = [Pj([mean] * n, np.diag( [factor[i]] * n ).dot( D ).dot( np.diag([factor[i]] * n) )) for i in range(len(factor)) ];
    return(P) 

### sampling from mixture densities
def mixture_sampling (N, alpha, P):
    K = len(alpha); choices = [i for i in range(K)]; count = [0] * K; input_df = pd.DataFrame();
    comp = np.random.choice(choices, N, replace = True, p = alpha);
    for i in range(len(comp)): count[comp[i]] += 1;
    for j in range(K):
        Pj_mean = P[j].means; Pj_cov = P[j].cov; Pj_N = count[j];
        Pj_df = pd.DataFrame(np.random.multivariate_normal(mean = Pj_mean, cov = Pj_cov, size = Pj_N));
        P[j].pdf = Pj_df
        input_df = input_df.append(Pj_df,ignore_index=True);
    return(input_df);

def h_t (ts,thres):
    return_vec = [0] * len(ts);
    for i in range(len(ts)):
        if(ts[i] >= thres): 
            return_vec[i] = 1;
    return(return_vec);

def P_density_estimation (P, input_df):
    nP = len(P); pdf_P = [];
    for i in range(nP):
        Pj_mean = P[i].means;
        Pj_cov = P[i].cov;
        Pj_pdf = MVN.pdf( x = input_df, mean = Pj_mean, cov = Pj_cov );
        pdf_P.append( np.array( Pj_pdf ) );
    return( pdf_P );

### These definitions are necessary for estimating I 
def const_mul(array, pdf_Pj):
    alist = [];
    for i in range(len(array)):
        amul = [array[i] * pdf_Pj[i][j] for j in range(len(pdf_Pj[i]))];
        alist.append(np.array(amul));
    return(alist);

def vector_sum(alist):
    sumvec = [0]*len(alist[0]);
    for i in range(len(alist)):
        sumvec = [sumvec[j] + alist[i][j] for j in range(len(alist[i]))];
    return(sumvec);

def estim_cov_tm(pdf_Pj, m):
    l = len(pdf_Pj);
    tm_vec = [0]*l;
    for i in range(l):
        tm_vec[i] = np.cov(m, pdf_Pj[i])[0][1];
    return(np.array(tm_vec));

def estim_cov_t(pdf_Pj, Palpha):
    l = len(pdf_Pj);
    t_mat = [];
    for i in range(l):
        array = np.array([pdf_Pj[i][j]/Palpha[j] for j in range(len(pdf_Pj[i]))])
        t_mat.append(array)
    return(np.cov(np.array(t_mat)));

def svd_inv(cov_t):
    u,s,v = np.linalg.svd(cov_t);

    ds = np.diag([1/s[j] for j in range(len(s)-1)]);
    us = np.matrix(u)[:,:-1];
    vs = np.matrix(np.transpose(v))[:,:-1];
    inv_cov_t = vs.dot(ds).dot(np.transpose(us));
    return(inv_cov_t)

def ims_estimate_statistics(df_data, n, w, t_v):
    df_out = pd.DataFrame(index = df_data.index)
    df_out['LL_RTS'] = df_data.apply(lambda x: vcm_optimization_IS(x.tolist(), n, w, t_v), axis=1)
    return(df_out)

def ims_parallelize(df_input, func, cores, partitions, n, w, t_v):
    data_split = np.array_split(df_input, partitions)
    iterable = product(data_split, [n], [w], [t_v])
    pool = mp.Pool(int(cores))
    df_output = pd.concat(pool.starmap(func, iterable))
    pool.close()
    pool.join()
    return(df_output)

def thres_estimate_pvalue(thres, Sdelpy, Palpha, alpha, d_Q, d_P, nPj, N):
    h = h_t(ts = Sdelpy, thres = thres);
    m = [h[i] * d_Q[i] / Palpha[i] for i in range(len(d_Q))];
    cov_tm = estim_cov_tm(d_P, m); 
    cov_t = estim_cov_t(d_P, Palpha);
    inv_cov_t = svd_inv(cov_t);
    denominator = vector_sum(const_mul(alpha, d_P));
    betas = [inv_cov_t.dot(cov_tm)[0,i] for i in range( nPj )];
    control_variate = vector_sum(const_mul(betas, d_P));
    nominator = [ h[i] * d_Q[i] - control_variate[i] for i in range(len( d_Q )) ];
    IS_estim = sum( nominator[i] / denominator[i] for i in range(len( d_Q ))) /N + np.sum( betas );
    return(pd.DataFrame([IS_estim], columns = ['pvalue'], index = [thres]))

def thres_parallelize(thres_vec, func, cores, Sdelpy, Palpha, alpha, d_Q, d_P, nPj, N):
    iterable = product(thres_vec, [Sdelpy], [Palpha], [alpha], [d_Q], [d_P], [nPj], [N])
    pool = mp.Pool(int(cores))
    res_list = pd.concat(pool.starmap(func, iterable))
    pool.close()
    pool.join()
    return(res_list)

## GenCor and RECor: np.matrix, N: int, outfn: str
def importance_sampling(N_impsamp, GWAS_nsamples, U, Ce, output_filename, Ncores, tol = 2.22044604925e-16**0.5):
    'Importance Sampling'
    ### we set random seed 
    np.random.seed(1)

    se = 1/(np.array(GWAS_nsamples)**0.5)
    N = N_impsamp
    
    ### set multi processing options 
    if(Ncores == 0):
        cores = mp.cpu_count() - 1; partitions = cores;
    else:
        cores = Ncores; partitions = cores;
    
    ### set parameters
    nstudy = len(se); n = nstudy; D = np.diag(se).dot(Ce).dot(np.diag(se));
    null_D = np.diag([1]*n).dot(Ce).dot(np.diag([1]*n))
    Uinv_sqrt = sqrt_ginv(U);
    K = np.transpose(Uinv_sqrt).dot(D).dot(Uinv_sqrt)
    w, v = np.linalg.eigh(K); t_v = np.transpose(v)
    pos = w > tol
    w_pos = w[pos]; t_v_pos = t_v[pos]

    ## PLEIO's importance sampling method reqiores probability densities to generate samples. They have means of [0] * n and the covariance matrix of c_Pj * Ce
    c_Pj = [1,1.1,1.2,1.3,1.4,1.7,2,2.5,3,4,5];

    nPj = len(c_Pj); mean_P = [0] * nPj; alpha = [1 / nPj] * nPj;   
    P = generate_P(0, c_Pj, null_D, n)
    
    ## generate sample X
    input_df = mixture_sampling(N, alpha, P)
    eta_df = input_df.multiply(se, axis = 1) 
    transformed_df = eta_df.apply(func = lambda x: Uinv_sqrt.dot(x), axis = 1, raw = True)
    print( "Generating {len_X} stats (this calculation is expected to take a long time).".format( len_X=N ) ); 
    
    
    #data = ims_parallelize( input_df, ims_estimate_statistics, cores, partitions, n, w, t_v )
    data = ims_parallelize( transformed_df, ims_estimate_statistics, cores, partitions, n, w_pos, t_v_pos )
    Sdelpy = data['LL_RTS'].tolist()

    d_Q = MVN.pdf( input_df, [0] * n, Ce );
    d_P = P_density_estimation( P, input_df );
   
    ### It is recommended to get tabulated pdf at 0.1, 0.2, 0.3 ... 1.0, 2.0, 3.0,.... 31.0.  
    #thres_vec = [ float(0.4)] ;
    thres_vec = np.append(np.append([0.0], np.logspace(-5,0, num=19, endpoint = False, base = 40, dtype = float)), np.logspace(0,1, num=20, endpoint = True, base = 40, dtype = float) )

    Palpha = vector_sum(const_mul(alpha,d_P));
   
    pvalue_df = thres_parallelize(thres_vec, thres_estimate_pvalue, cores, Sdelpy, Palpha, alpha, d_Q, d_P, nPj, N)
    print('Complete CDF estimation for distributed component model.'); 
    
    sorted_pvalue = pvalue_df.sort_index()
    print(sorted_pvalue)
    sorted_pvalue.to_csv(output_filename, header = False, index = True, sep = " ")
    print('Wrote tabulated inverse cdf');
