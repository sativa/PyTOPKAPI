""" TOPKAPI_main.py
Main programm of the hydrological model.
"""

__author__ = "Theo Vischel"
__version__ = "$Revision: 1.0 $"
__date__ = "$Date: 08/10/2006 $"

import sys
############################################
############################################
sys.path.append('c:/Theo/topkapi_model/programme/')
sys.path.append('c:/Theo/liebenbergsvlei/python_prog/')

#General module importation
import numpy as np
import scipy as sp
import tables as h5
import scipy.io as io

#Personnal module importation
import utils as ut
import pretreatment as pm
import fluxes as fl
import ode as om
import evap as em
reload(ut)
reload(pm)
reload(fl)
reload(om)
reload(em)


def run(input_file):

    ##~~~~~~ Numerical options ~~~~~~##
    solve_s=1 #0 for RKF, 1 for qas/RKF
    solve_o=1 #0 for RKF, 1 for qas/RKF
    solve_c=1 #0 for RKF, 1 for qas/RKF

    ##~~~~~~ Result writing options~~~~~##
    only_channel_output=False

    ##~~~~~~~~~~~ INPUTS  ~~~~~~~~~~~##
    #Initial soil moisture and parameter factors
    Vs_initial=40.
    fac_L=1.1
    fac_Ks=101.
    fac_n_o=1.
    fac_n_c=1.

    #Param
    path_in='C:/Theo/topkapi_model/programme/TOPKAPI_Aug07/Example/'
    file_global_param=path_in+'global_param.dat'
    file_cell_param=path_in+'cell_param.dat'
    #Rain
    path_rain=path_in+'forcing_variables/'
    file_rain=path_rain+'rainfields.h5'
    #ETP
    path_ET=path_in+'forcing_variables/'
    file_ET=path_ET+'ET.h5'
    #Event
    group_name='sample_event'

    #LESOTHO
    lesotho=False
    if lesotho:
        path_Qlesotho=path_in+'forcing_variables/'
        file_Qlesotho=path_Qlesotho+'external_lesotho_flows.dat'



    ##~~~~~~~~~~~ OUTPUTS FILES ~~~~~~~~~~##
    path_out=path_in+'Results/'
    #create path_out if it does'nt exist
    ut.check_folder_exist(path_out)

    file_out=path_out+group_name+'_simulation_results.h5'

    ##################################
    ##~~~~~~~~~~ PROGRAMME ~~~~~~~~~##
    ##################################

    ####----------------------------####
    ####   Read the forcing data    ####
    ####----------------------------####

    ##~~~~~~~~~~~ Input files ~~~~~~~~~~~##
    ###~~~~Rainfall file reading
    #Read the data
    h5file_in=h5.openFile(file_rain,mode='r')
    group='/'+group_name+'/'
    node = h5file_in.getNode(group+'rainfall')
    ndar_rain=node.read()
    h5file_in.close()

    ###~~~~ETr 
    h5file_in=h5.openFile(file_ET,mode='r')
    group='/'+group_name+'/'
    node = h5file_in.getNode(group+'ETr')
    ndar_ETr=node.read()
    h5file_in.close()

    ###~~~~ETo
    h5file_in=h5.openFile(file_ET,mode='r')
    group='/'+group_name+'/'
    node = h5file_in.getNode(group+'ETo')
    ndar_ETo=node.read()
    h5file_in.close()

    ###~~~~Lesotho flows
    #read the flow data coming from lesotho
    if lesotho:
        ar_Qlesotho=io.read_array(file_Qlesotho)[:,5]

    ####----------------------------####
    #### Pretreatment of input data ####
    ####----------------------------####

    ##~~~~~~~~~~~ Parameters ~~~~~~~~~~~##
    #~~~~Read Global parameters file
    X,Dt,alpha_s,alpha_o,alpha_c,A_thres,W_min,W_max\
      =pm.read_global_parameters(file_global_param)
    #~~~~Read Cell parameters file
    ar_cell_label,ar_coorx,ar_coory,ar_lambda,ar_tan_beta,ar_L1,ar_Ks1,\
    ar_theta_r,ar_theta_s,ar_n_o1,ar_n_c1,\
    ar_cell_down,ar_pVs_t0,ar_pVc_t0,ar_kc\
        =pm.read_cell_parameters(file_cell_param)
    ar_tan_beta[ar_tan_beta==0.]=1e-3
    #~~~~Number of cell in the catchment
    nb_cell=len(ar_cell_label)
    #~~~~Computation of cell order
    ar_label_sort=pm.sort_cell(ar_cell_label,ar_cell_down)
    #~~~~Computation of upcells
    li_cell_up=pm.direct_up_cell(ar_cell_label,ar_cell_down,ar_label_sort)
    #~~~~Computation of drained area
    ar_A_drained=pm.drained_area(ar_label_sort,li_cell_up,X)

    #~~~~Look for the cell of Lesotho tunnel
    if lesotho:
        Xlesotho=-255032.83
        Ylesotho=-3149857.34
        cell_lesotho=ut.find_cell_coordinates(ar_cell_label,Xlesotho,Ylesotho,ar_coorx,ar_coory,ar_lambda)

    ###############################################  
    ######Change the values of the parameters######
    ###############################################
    ar_L=ar_L1*fac_L
    ar_Ks=ar_Ks1*fac_Ks
    ar_n_o=ar_n_o1*fac_n_o
    ar_n_c=ar_n_c1*fac_n_c

    ####---------------------------------####
    #### Computation of model parameters ####
    ####---------------------------------####

    #~~~~Computation of model parameters from physical parameters
    ar_Vsm, ar_b_s, ar_Vs_t0, ar_b_o, ar_W, ar_b_c, ar_Vc_t0\
      =pm.compute_cell_param(X,Dt,alpha_s,alpha_o,alpha_c,nb_cell,\
                              A_thres,W_max,W_min,\
                              ar_lambda,ar_tan_beta,ar_L,\
                              ar_Ks,ar_theta_r,ar_theta_s,ar_n_o,ar_n_c,\
                              ar_A_drained,ar_pVs_t0,ar_pVc_t0)


    ####---------------------------####
    ####     Some changes for      ####
    ####   sensitivity analyses    ####
    ####---------------------------####

    #~~~~Number of simulation time steps
    nb_time_step=len(ndar_rain[:,0])

    ####---------------------------####
    ####     Core of the Model     ####
    ####---------------------------####
    print 'NB_CELL=',nb_cell
    print 'NB_TIME_STEP=',nb_time_step
    print '**SIMULATIONS**'


    ####=============================####
    ####  Variable array definition  ####
    ####=============================####

    ## All these variables are computed
    ##==================================####
    ## Initialisation of the reservoirs ####
    ##==================================####
    #Matrix of soil,overland and channel store at the begining of the time step
    ar_Vs0=ar_Vs_t0
    ar_Vo0=sp.zeros(nb_cell)
    if lesotho:
        ar_Qc_ini=sp.zeros(nb_cell)+ar_Qlesotho[0]
        ar_Vc_t0=fl.initial_volume_channel(ar_Qc_ini,ar_W,X,ar_n_c)
    ar_Vc0=ar_Vc_t0
    #Matrix of soil,overland and channel store at the end of the time step
    ar_Vs1=sp.ones(nb_cell)*-99.9
    ar_Vo1=sp.ones(nb_cell)*-99.9
    ar_Vc1=sp.ones(nb_cell)*-99.9
    #Matrix of outflows between two time steps
    ar_Qs_out=sp.ones(nb_cell)*-99.9
    ar_Qo_out=sp.ones(nb_cell)*-99.9
    ar_Qc_out=sp.zeros(nb_cell)

    ## Intermediate validation variables
    #Matrix of soil,overland and channel total input
    ar_a_s=sp.ones(nb_cell)*-99.9
    ar_a_o=sp.ones(nb_cell)*-99.9
    ar_a_c=sp.ones(nb_cell)*-99.9
    ar_Q_to_next_cell=sp.ones(nb_cell)*-99.9
    ar_Q_to_channel=sp.ones(nb_cell)*-99.9
    ar_Q_to_channel_sub=sp.zeros(nb_cell)
    ar_Qc_cell_up=sp.zeros(nb_cell)

    ar_ETa=sp.zeros(nb_cell)
    ar_ET_channel=sp.zeros(nb_cell)
      

    ##=============================####
    ## HDF5 output file definition ####
    ##=============================####
    h5file=h5.openFile(file_out,mode='w',title='TOPKAPI_out')

    atom = h5.Float32Atom(shape=(0,nb_cell))# needs to match your data type
    h5filter = h5.Filters(9)# maximum compression

    group_soil=h5file.createGroup('/','Soil','Soil arrays')
    array_Vs = h5file.createEArray(group_soil, 'V_s', atom,'m3', \
                                    filters=h5filter,expectedrows=nb_time_step+1)
    group_overland=h5file.createGroup('/','Overland','Overland arrays')
    array_Vo = h5file.createEArray(group_overland, 'V_o', atom,'m3', \
                                    filters=h5filter,expectedrows=nb_time_step+1)
    group_channel=h5file.createGroup('/','Channel','Channel arrays')
    array_Qc_out = h5file.createEArray(group_channel, 'Qc_out', atom,'m3/s', \
                                    filters=h5filter,expectedrows=nb_time_step)


    ##Write some initial values into the output file
    array_Vs.append(ar_Vs0.reshape((1,nb_cell)))
    array_Vo.append(ar_Vo0.reshape((1,nb_cell)))

    ## Loop on time
    for t in range(nb_time_step):
        print t

        ## Loop on cells
        n=-1
        for cell1 in ar_label_sort:
            cell=np.where(ar_cell_label==cell1)[0][0]
            n=n+1
           

            ## ======================== ##       
            ## ===== INTERCEPTION ===== ##
            ## ======================== ##
            ## No interception for the moment
            
            ## ====================== ##       
            ## ===== SOIL STORE ===== ##
            ## ====================== ##
            #~~~~ Computation of soil input        
            ar_a_s[cell] \
                = fl.input_soil(ndar_rain[t,cell],Dt,X,ar_Q_to_next_cell,li_cell_up[cell])
            #~~~~ Resolution of the equation dV/dt=a_s-b_s*V^alpha_s
            if ar_a_s[cell]==0.:
                Vs_prim=om.input_zero_solution(ar_b_s[cell], alpha_s, ar_Vs0[cell], Dt)
            elif ar_b_s[cell]==0.:
                Vs_prim=om.coefb_zero_solution(ar_a_s[cell], ar_Vs0[cell], Dt)
            else:
                if solve_s==1:
                    #qas
                    Vs_prim =om.qas(ar_a_s[cell], ar_b_s[cell], alpha_s, ar_Vs0[cell], Dt)
                    if(Vs_prim-ar_Vs0[cell])/Dt > ar_a_s[cell]:
                        #Definition of the convergence error
                        if(ar_Vs0[cell]==0.):
                            err_min=1e-7;err_max=1e-3
                        else:
                            err_min=1e-7/100.*ar_Vs0[cell];err_max=10e-3/100.*ar_Vs0[cell]
                        #RKF
                        f=om.fonction(ar_a_s[cell],ar_b_s[cell],alpha_s)
                        cl_a = om.RKF(min_step=10e-10, max_step=Dt,\
                                      min_tol=err_min, max_tol=err_max,\
                                      init_time_step=Dt)
                        Vs_prim =cl_a.step(f,ar_Vs0[cell], 0, Dt)
                if solve_s==0:
                    #Definition of the convergence error
                    if(ar_Vs0[cell]==0.):
                        err_min=1e-7;err_max=1e-3
                    else:
                        err_min=1e-7/100.*ar_Vs0[cell];err_max=10e-3/100.*ar_Vs0[cell]
                    #RKF
                    f=om.fonction(ar_a_s[cell],ar_b_s[cell],alpha_s)
                    cl_a = om.RKF(min_step=10e-10, max_step=Dt,\
                                  min_tol=err_min, max_tol=err_max,\
                                  init_time_step=Dt)
                    Vs_prim =cl_a.step(f,ar_Vs0[cell], 0, Dt)
                    
            #~~~~ Computation of soil outlflow and overland input
            ar_Qs_out[cell],ar_Vs1[cell] \
                = fl.output_soil(ar_Vs0[cell],Vs_prim,ar_Vsm[cell],ar_a_s[cell],ar_b_s[cell],alpha_s,Dt)
            if ar_Qs_out[cell]<0:
                print 'Problem Soil:output greater than input....'
                print 'n=',n,'label=',cell
                stop

            ## ========================== ##
            ## ===== OVERLAND STORE ===== ##
            ## ========================== ##
            #~~~~ Computation of overland input        
            if Vs_prim > ar_Vsm[cell]:
                ar_a_o[cell]=max(0.,ar_a_s[cell]-((ar_Vs1[cell]-ar_Vs0[cell])/Dt+ar_Qs_out[cell]))
            else:
                ar_a_o[cell]=0.
             
            #~~~~ Resolution of the equation dV/dt=a_o-b_o*V^alpha_o
            if ar_a_o[cell]==0.:
                #print 'Shortcut Overland a_o=0'
                ar_Vo1[cell]=om.input_zero_solution(ar_b_o[cell], alpha_o, ar_Vo0[cell], Dt)
            elif ar_b_o[cell]==0.:
                Vs_prim=om.coefb_zero_solution(ar_a_o[cell], ar_Vo0[cell], Dt)
            else:
                if solve_o==1:
                    #qas
                    ar_Vo1[cell] = om.qas(ar_a_o[cell], ar_b_o[cell], alpha_o, ar_Vo0[cell], Dt)
                    if(ar_Vo1[cell]-ar_Vo0[cell])/Dt > ar_a_o[cell]:
                        #Definition of the convergence error
                        if(ar_Vo0[cell]==0.):
                            err_min=1e-7;err_max=1e-3
                        else:
                            err_min=1e-7/100.*ar_Vo0[cell];err_max=1e-3/100.*ar_Vo0[cell]
                        #RKF
                        f=om.fonction(ar_a_o[cell],ar_b_o[cell],alpha_o)
                        cl_a = om.RKF(min_step=10e-10, max_step=Dt,\
                                      min_tol=err_min, max_tol=err_max,\
                                      init_time_step=Dt)
                        ar_Vo1[cell] = cl_a.step(f,ar_Vo0[cell], 0, Dt)
                if solve_o==0:
                    #Definition of the convergence error
                    if(ar_Vo0[cell]==0.):
                        err_min=1e-7;err_max=1e-3
                    else:
                        err_min=1e-7/100.*ar_Vo0[cell];err_max=1e-3/100.*ar_Vo0[cell]
                    #RKF
                    f=om.fonction(ar_a_o[cell],ar_b_o[cell],alpha_o)
                    cl_a = om.RKF(min_step=10e-10, max_step=Dt,\
                                  min_tol=err_min, max_tol=err_max,\
                                  init_time_step=Dt)
                    ar_Vo1[cell] = cl_a.step(f,ar_Vo0[cell], 0, Dt)
                

            #~~~~ Computation of overland outlflows
            ar_Qo_out[cell] \
                = fl.Qout_computing(ar_Vo0[cell],ar_Vo1[cell],ar_a_o[cell],Dt)
            if ar_Qo_out[cell]<0:
                print 'Problem Overland:output greater than input....'
                print 'n=',n,'label=',cell
                stop

            ## ============================= ##
            ## ===== FLOW PARTITIONING ===== ##
            ## ============================= ##
            ar_Q_to_next_cell[cell],ar_Q_to_channel[cell],ar_Q_to_channel_sub[cell] \
                = fl.flow_partitioning(ar_lambda[cell],ar_Qs_out[cell],\
                                       ar_Qo_out[cell],ar_W[cell],X)


            ## ======================== ##
            ## ===== CHANNEL STORE ==== ##
            ## ======================== ##
            if ar_lambda[cell]==1:
                if ar_cell_down[cell]>=0 and ar_lambda[ar_cell_down[cell]]==0:
                    print 'Problem: the present cell has a channel but not the cell down...'
                    Stop
                #~~~~ Computation of channel input
                ar_a_c[cell],ar_Qc_cell_up[cell] \
                    = fl.input_channel(ar_Qc_out,ar_Q_to_channel[cell],li_cell_up[cell])
                
                if lesotho and cell==np.where(ar_cell_label==cell_lesotho)[0][0]:
                    ar_a_c[cell]=ar_a_c[cell]+ar_Qlesotho[t]

                #~~~~ Resolution of the equation dV/dt=a_c-b_c*V^alpha_c
                if ar_a_c[cell]==0.:
                    ar_Vc1[cell]=om.input_zero_solution(ar_b_c[cell], alpha_c, Vc[t,cell], Dt)
                elif ar_b_c[cell]==0.:
                    Vs_prim=om.coefb_zero_solution(ar_a_c[cell], ar_Vc0[cell], Dt)
                else:
                    if solve_c==1:
                        #qas
                        ar_Vc1[cell] = om.qas(ar_a_c[cell],ar_b_c[cell], alpha_c, ar_Vc0[cell], Dt)
                        if(ar_Vc1[cell]-ar_Vc0[cell])/Dt > ar_a_c[cell]:
                            #Definition of the convergence error
                            if(ar_Vc0[cell]==0.):
                                err_min=1e-7;err_max=1e-3
                            else:
                                err_min=1e-7/100.*ar_Vc0[cell];err_max=1e-3/100.*ar_Vc0[cell]
                            #RKF
                            f=om.fonction(ar_a_c[cell],ar_b_c[cell],alpha_c)
                            cl_a = om.RKF(min_step=10e-10, max_step=Dt,\
                                          min_tol=err_min, max_tol=err_max,\
                                          init_time_step=Dt)
                            ar_Vc1[cell] = cl_a.step(f,ar_Vc0[cell], 0, Dt)
                             
                    if solve_c==0:
                        #Definition of the convergence error
                        if(ar_Vc0[cell]==0.):
                            err_min=1e-7;err_max=1e-3
                        else:
                            err_min=1e-7/100.*ar_Vc0[cell];err_max=1e-3/100.*ar_Vc0[cell]
                        #RKF
                        f=om.fonction(ar_a_c[cell],ar_b_c[cell],alpha_c)
                        cl_a = om.RKF(min_step=10e-10, max_step=Dt,\
                                      min_tol=err_min, max_tol=err_max,\
                                      init_time_step=Dt)
                        ar_Vc1[cell] = cl_a.step(f,ar_Vc0[cell], 0, Dt)

                #~~~~ Computation of channel outlflows
                ar_Qc_out[cell] \
                    = fl.Qout_computing(ar_Vc0[cell],ar_Vc1[cell],ar_a_c[cell],Dt)
                if ar_Qc_out[cell]<0:
                    print 'Problem Channel: output greater than input....'
                    stop
                if str(ar_Qc_out[cell]).count('N')>0:
                    print ar_Qc_out[cell]
                    print 'Problem Channel: Non authorized operand....'
                    stop
                
            else:
                ar_a_c[cell] = 0.
                ar_Vc1[cell] = 0.
                ar_Qc_out[cell] = 0.

            
            ## ============================== ##
            ## ===== EVAPOTRANSPIRATION ===== ##
            ## ============================== ##
            #~~~~~ From soil
            ar_ETa[cell],ar_Vs1[cell],ar_Vo1[cell]=\
            em.evapot_soil_overland(ar_Vo1[cell],ar_Vs1[cell],ar_Vsm[cell],ar_kc[cell],ndar_ETr[t,cell],X)

            #~~~~~ Evaporation from channel
            if ar_lambda[cell]==1:
                 ar_ET_channel[cell],ar_Vc1[cell]=em.evapor_channel(ar_Vc1[cell],ndar_ETo[t,cell],ar_W[cell],X)

        ####===================================####
        #### Affectation of new vector values  ####
        ####===================================####
        ar_Vs0=np.array(ar_Vs1)
        ar_Vo0=np.array(ar_Vo1)
        ar_Vc0=np.array(ar_Vc1)

        ####===================================####
        #### Results writing at each time step ####
        ####===================================####

        array_Vs.append(ar_Vs1.reshape((1,nb_cell)))
        array_Vo.append(ar_Vo1.reshape((1,nb_cell)))
        array_Qc_out.append(ar_Qc_out.reshape((1,nb_cell))) 

    h5file.close()

    print ' '
    print '***** THE END *****'
