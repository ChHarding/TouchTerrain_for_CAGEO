''' Calculates nice ticks for elevation axis'''
# 1. Calculate the range of the elevations
# 2. Loop through the thresholds given by a dictionary
# 3. Check if the range is less than the current threshold
# 4. Get the step size for the current threshold
# 5. Calculate the nice minimum elevation value
# 6. Generate the ticks using the step size 
# 7. Check if the first tick is far enough from the minimum elevation
# 8. Add the minimum elevation as a tick
# 9. Check if the last tick is far enough from the maximum elevation
# 10. Add the maximum elevation as a tick
# 11. Return the ticks

# Notes: The defaults are for elevations on earth. The function should work for any range of elevations and step sizes
# given the appropriate thresholds and step sizes. Works with negative values as well.


def calculate_ticks(elevmin, elevmax, step_sizes = {
        10: 2,
        50: 10,   
        100: 25,  
        250: 50,
        500: 100,
        1000: 250,
        2500: 500,
        5000: 1000,
        10000: 5000,
    }):
    ''' Calculate ticks for given min and max elevation in nice steps
        in: (numbers) elevmin, elevmax: min and max elevation
        in: (step_sizes: dictionary with thresholds and step sizes, defaults are for elevations on earth
        out: list with ticks or [] if no ticks could be calculated
    '''
    
    def next_multiple_of_step(number, step):
        """
        For positive numbers, calculate the next multiple of the step size that is >= to the given number.
        For negative numbers, the next multiple is <= to the given number.
            in: number (int): The number to round up. (or down if the number is negative)
            in: step (int): The step size to round to.
            out: int: The next multiple of the step size that is greater than or equal to the given number

        Examples:
            >>> next_multiple_of_step(718, 50)  # positive rounds up
            750
            >>> next_multiple_of_step(-54, 10)  # negative rounds down
            -50
            >>> next_multiple_of_step(123, 25)
            125
        """  
        return ((number + step - 1) // step) * step  

    # make ints of the elevations (could be floats)
    elevmin, elevmax = int(elevmin), int(elevmax)
    rnge = elevmax - elevmin

    # Loop through the thresholds   
    for threshold in step_sizes.keys():
        # Check if the range is less than the current threshold
        if rnge < threshold:
            # Get the step size for the current threshold
            step_size = step_sizes[threshold]

            # Calculate the nice minimum elevation value
            nice_elevmin = next_multiple_of_step(elevmin, step_size)

            # Generate the ticks using the step size
            ticks = list(range(nice_elevmin, elevmax + step_size, step_size))[:-1]

            # Check if the first tick is far enough from the minimum elevation
            if ticks[0] - elevmin > step_size/2:
                # Add the minimum elevation as a tick
                ticks = [elevmin] + ticks
                #print(step_size/2, "min", end=" ") # debug to see if min tick is added and for what distance

            # Check if the last tick is far enough from the maximum elevation
            if elevmax - ticks[-1] > step_size/2:
                # Add the maximum elevation as a tick
                ticks = ticks + [elevmax]
                #print(step_size/2, "max", end=" ") # debug to see if min tick is added and for what distance

            return ticks

    # Handle the case where rnge is larger than any threshold  
    return []



if __name__ == "__main__":

    # Test the function
    elevmin = 20
    elevmax = 130
    #print(elevmin, elevmax, elevmax-elevmin, calculate_ticks(elevmin, elevmax)) 

    # random numbers test
    import random
    for i in range(10):
        elevmin = random.randint(-500, 6000)
        elevmax = elevmin + random.randint(100, 1000)   
        ticks = calculate_ticks(elevmin, elevmax)
        print(f"min: {elevmin:4d}  max: {elevmax:4d}  range: {elevmax-elevmin:4d}", " ticks:", ticks)


