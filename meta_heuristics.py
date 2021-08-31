import numpy as np
import random
import copy
import math


class MetaHeuristics(object):

    def __init__(self, uhe_data, n_ug, n_days, maintenance_round, maintenance_duration, previous_calendar,
                 n_ind):

        self.start_individuals = {}
        self.possible_days = None
        self.dict_of_days = None

        self.best_fob_result = None
        self.best_bat_result = None
        self.evolution = None

        self.n_ug = n_ug
        self.n_days = n_days
        self.current_round = maintenance_round
        self.maintenance_duration = maintenance_duration

        self.initialize_individual(uhe_data=uhe_data, previous_calendar=previous_calendar, n_ind=n_ind)

    def initialize_individual(self, uhe_data, previous_calendar, n_ind):

        dict_of_days = {}
        maintenance_round = self.current_round
        current_maintenance = self.maintenance_duration[:, maintenance_round]
        self.possible_days = np.zeros(shape=(self.n_ug, self.n_days))

        for ug in range(self.n_ug):

            # Select possible days to start maintenance
            maintenance = int(current_maintenance[ug])

            # rfo limitation
            ug_rfo = uhe_data.rfo_dia[ug, :]
            for day in range(self.n_days):
                if ug_rfo[day] == 1:  # Days with rfo are not possible
                    if day - maintenance > 0:
                        self.possible_days[ug, day - maintenance: day] = 1
                    else:
                        self.possible_days[ug, 0:day] = 1
            self.possible_days[ug, self.n_days - maintenance:self.n_days] = 1  # Maintenance must be completed

            # maintenance limitation
            ug_previous_calendar = previous_calendar[ug, :]
            for day in range(self.n_days):
                if ug_previous_calendar[day] == 1:  # Days with maintenance are not possible
                    if day - maintenance > 0:
                        self.possible_days[ug, day - maintenance: day] = 1
                    else:
                        self.possible_days[ug, 0:day] = 1
            self.possible_days[ug, self.n_days - maintenance:self.n_days] = 1

            # Maintenance start for each ug
            list_of_days = []
            for day in range(self.n_days):
                if self.possible_days[ug, day] == 0:
                    list_of_days.append(day)

            lim_1 = 150
            lim_2 = 30
            filter_1 = [x for x in list_of_days if lim_1 <= x]
            # filter_2 = [x for x in list_of_days if lim_2 >= x]
            filter_2 = []
            dict_of_days[ug] = filter_2 + filter_1
            if not dict_of_days[ug]:
                dict_of_days[ug] = list_of_days

        # Initialize heuristic individuals
        self.dict_of_days = dict_of_days
        individuals = {}

        for ind in range(n_ind):
            individual = np.zeros(shape=(self.n_ug, self.n_days))
            individuals[ind] = {}
            start_days = []
            for ug in range(self.n_ug):
                maintenance = int(current_maintenance[ug])
                possible_days = dict_of_days[ug]
                start_day = random.choice(possible_days)
                start_days.append(start_day)
                individual[ug, start_day:start_day + maintenance] = 1

                individuals[ind]['start_days'] = start_days
                individuals[ind]['calendar'] = individual

        self.start_individuals = individuals

    @staticmethod
    def check_bat_bounds(n_ug, current_bat, upper_lim, lower_lim, dict_of_days, maintenance_round):
        # feb: 30 to 60
        # march: 60 to 90
        # april: 90 to 120
        # may: 120 to 150
        limbo_min = 30
        limbo_max = 150
        for ug in range(n_ug):
            days = dict_of_days[ug]
            if current_bat[ug] > upper_lim[ug]:
                current_bat[ug] = upper_lim[ug]

            if current_bat[ug] < lower_lim:
                current_bat[ug] = lower_lim

            if limbo_min < current_bat[ug] < limbo_max:
                limbo_list = [limbo_min, limbo_max]
                current_bat[ug] = min(limbo_list, key=lambda x: abs(x - current_bat[ug]))

            if int(current_bat[ug]) not in days:
                array = np.asarray(days)
                value = current_bat[ug]
                idx = (np.abs(array - value)).argmin()
                current_bat[ug] = array[idx]

        return current_bat

    def bat_algorithm_process(self, uhe_data, previous_calendar, vt_data, n_gen, alpha, lbd, n_ind, maintenance_round,
                              original_operation, original_spill):

        ind_size = self.n_ug  # individual size
        pop_size = n_ind  # denotes population size,

        t = 1  # iteration count
        a_loud = np.ones(pop_size)  # initial loudness
        # r = (1 - np.exp(-lbd * t)) * a_loud       # initial pulse rates
        r = 0 * a_loud  # initial pulse rates
        v = np.zeros(shape=(pop_size, ind_size))  # initial speeds

        lower_lim = 0
        upper_lim = []

        current_maintenance = self.maintenance_duration[:, self.current_round]

        for ug in range(self.n_ug):
            upper_lim.append(self.n_days - current_maintenance[ug])

        fobs = []
        individuals = copy.deepcopy(self.start_individuals)
        inflow = uhe_data.vaz_afl

        # evaluate all start individuals
        for individual in individuals.values():
            start_days = individual['start_days']
            operation = copy.deepcopy(original_operation)
            spilled = copy.deepcopy(original_spill)

            individual_spilled = self.heuristic(n_ug=self.n_ug, vt_data=vt_data, operation=operation, spilled=spilled,
                                                start_days=start_days, maintenance_duration=current_maintenance)

            individual_spilled = np.asarray(individual_spilled)
            weighted_fob = individual_spilled * inflow / sum(inflow)
            # individual_spilled = weighted_fob

            fobs.append(sum(individual_spilled))

        # get best initial bat
        best_fob = min(fobs)
        best_bat_idx = fobs.index(best_fob)
        best_bat = individuals[best_bat_idx]['start_days']
        best_bat = np.asarray(best_bat)

        self.evolution = [best_fob]

        def sigmoid_function(x):
            return 1 / (1 + math.exp(-x))

        t = 1
        while t <= n_gen:
            generation_fobs = []
            print('----------- Generation %i -----------' % t)
            for ind in range(pop_size):  # parallelize here: if its parallel, we can use a high number of bats

                # update bat

                beta = np.random.random()
                bat = np.asarray(individuals[ind]['start_days'])
                v[ind, :] = v[ind, :] + (best_bat - bat) * beta
                current_bat = bat + v[ind, :]

                # local search

                rand = np.random.random()
                if rand < r[ind]:
                    e = np.ones(ind_size) * np.random.random()
                    current_bat = best_bat + e * a_loud[ind]

                # verify lower and upper violations

                current_bat = self.check_bat_bounds(n_ug=self.n_ug, current_bat=current_bat,
                                                    upper_lim=upper_lim, lower_lim=lower_lim,
                                                    dict_of_days=self.dict_of_days, maintenance_round=maintenance_round)

                # global search

                bat = np.ceil(current_bat)  # round to the next integer - in the future use sigmoid instead
                # for ug in range(self.n_ug):
                #     current_bat[ug] = np.round(sigmoid_function(current_bat[ug]))

                start_days = bat.astype(int)
                operation = copy.deepcopy(original_operation)
                spilled = copy.deepcopy(original_spill)

                individual_spilled = self.heuristic(n_ug=self.n_ug, vt_data=vt_data,
                                                    operation=operation, spilled=spilled,
                                                    start_days=start_days, maintenance_duration=current_maintenance)

                individual_spilled = np.asarray(individual_spilled)
                weighted_fob = individual_spilled * inflow / sum(inflow)
                individual_spilled = weighted_fob

                current_fob = sum(individual_spilled)
                generation_fobs.append(current_fob)

                # update bat parameters

                rand = np.random.random()
                if rand < a_loud[ind] and current_fob <= fobs[ind]:
                    individuals[ind]['start_days'] = current_bat
                    r[ind] = (1 - np.exp(-lbd * t))
                    a_loud[ind] = alpha * a_loud[ind]

            # verify and update the new best fob

            for f, fob in enumerate(generation_fobs):
                if fob < best_fob:
                    print('Found super new best')
                    best_fob = fob
                    best_bat = individuals[f]['start_days']
                    # break

                if fob <= best_fob:
                    print('Found new best')
                    best_fob = fob
                    best_bat = individuals[f]['start_days']
                    break

            self.evolution.append(best_fob)
            t += 1

        best_fob_result = best_fob
        best_bat_result = np.round(best_bat)
        print('-------------------------------------')

        self.best_fob_result = best_fob_result
        self.best_bat_result = best_bat_result

    @staticmethod
    def heuristic(n_ug, vt_data, operation, spilled, start_days, maintenance_duration):

        # get vt max as an array
        vt_array = np.array([vt_data.vt_max[ug] for ug in range(n_ug)])

        # update daily operation state
        # current_spill = list(spilled)
        # current_operation = np.asarray(operation)
        current_spill = spilled
        current_operation = operation
        # sort ug order based on their maintenance duration
        ug_sorted = [x for _, x in sorted(zip(maintenance_duration, np.arange(0, n_ug)))]
        ug_sorted = ug_sorted[::-1]

        for ug in ug_sorted:
            # get start and duration of maintenance
            start = start_days[ug]
            duration = maintenance_duration[ug]
            days = np.arange(start, start + duration, 1)

            for day in days:
                day = int(day)
                # get operation state for all ug and for current ug
                daily_all_ug_operation = current_operation[:, day].astype(int)
                daily_all_ug_operation[ug] = 2
                daily_ug_operation = int(current_operation[ug, day])

                # get daily max turbined value for all ug and for current ug
                daily_all_vt_max = vt_array[:, day]
                daily_ug_vt_max = vt_array[ug, day]

                if daily_ug_operation == 0:
                    # spill don't change
                    flag = 99
                elif daily_ug_operation == 1:
                    if 0 in daily_all_ug_operation:  # has available ug: don't need to spill all
                        # find similar ug
                        ug_equal = np.where(daily_all_vt_max == daily_ug_vt_max)[0]
                        ug_different = np.where(daily_all_vt_max != daily_ug_vt_max)[0]

                        flag = 0
                        for new_ug in ug_equal:
                            if int(daily_all_ug_operation[new_ug]) == 0 and ug != new_ug and flag == 0:
                                daily_all_ug_operation[new_ug] = 1
                                flag = 1

                        if flag == 0:
                            for new_ug in ug_different:
                                if int(daily_all_ug_operation[new_ug]) == 0 and flag == 1:
                                    daily_all_ug_operation[new_ug] = 1
                                    turbined_difference = daily_ug_vt_max - daily_all_vt_max[new_ug]

                                    current_spill[day] = np.max([turbined_difference, 0])
                                    flag = 2

                    else:  # do not have an available ug: spill this day
                        current_spill[day] += daily_ug_vt_max
                # only need this after find the best
        return current_spill