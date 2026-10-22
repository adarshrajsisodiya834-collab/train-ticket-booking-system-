# fare_engine.py

"""
RailBook Fare Engine

Calculates train fares based on:
- Distance travelled
- Travel class
- Train category

This module is intentionally independent from Flask/database code.
"""


# ---------------------------------------------------------
# Base fare configuration
# ---------------------------------------------------------

BASE_RATE_PER_KM = 0.60


# ---------------------------------------------------------
# Travel class multipliers
# ---------------------------------------------------------

CLASS_MULTIPLIER = {
    "SL": 1.00,   # Sleeper
    "3A": 1.80,   # AC 3 Tier
    "2A": 2.50,   # AC 2 Tier
    "1A": 3.50    # First AC
}


# ---------------------------------------------------------
# Train category multipliers
# ---------------------------------------------------------

TRAIN_MULTIPLIER = {
    "NORMAL": 1.00,
    "EXPRESS": 1.10,
    "SUPERFAST": 1.20,
    "RAJDHANI": 1.35,
    "SHATABDI": 1.30
}


# ---------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------

def get_class_multiplier(travel_class):
    """
    Return the multiplier for a travel class.
    """

    travel_class = travel_class.upper().strip()

    if travel_class not in CLASS_MULTIPLIER:
        raise ValueError(
            f"Invalid travel class: {travel_class}. "
            f"Allowed classes: {', '.join(CLASS_MULTIPLIER.keys())}"
        )

    return CLASS_MULTIPLIER[travel_class]


def get_train_multiplier(train_type):
    """
    Return the multiplier for a train category.
    """

    if not train_type:
        return TRAIN_MULTIPLIER["NORMAL"]

    train_type = train_type.upper().strip()

    return TRAIN_MULTIPLIER.get(
        train_type,
        TRAIN_MULTIPLIER["NORMAL"]
    )


# ---------------------------------------------------------
# Main fare calculation
# ---------------------------------------------------------

def calculate_fare(
    distance_km,
    travel_class,
    train_type="NORMAL"
):
    """
    Calculate fare for a journey.

    Parameters
    ----------
    distance_km : float
        Distance travelled in kilometres.

    travel_class : str
        One of:
        SL, 3A, 2A, 1A

    train_type : str
        One of:
        NORMAL, EXPRESS, SUPERFAST, RAJDHANI, SHATABDI

    Returns
    -------
    int
        Calculated fare in rupees.
    """

    # -----------------------------
    # Validate distance
    # -----------------------------

    try:
        distance_km = float(distance_km)
    except (TypeError, ValueError):
        raise ValueError("Distance must be a number.")

    if distance_km <= 0:
        raise ValueError("Distance must be greater than 0.")


    # -----------------------------
    # Get multipliers
    # -----------------------------

    class_multiplier = get_class_multiplier(travel_class)

    train_multiplier = get_train_multiplier(train_type)


    # -----------------------------
    # Calculate base fare
    # -----------------------------

    base_fare = distance_km * BASE_RATE_PER_KM


    # -----------------------------
    # Apply class and train factors
    # -----------------------------

    fare = (
        base_fare
        * class_multiplier
        * train_multiplier
    )


    # -----------------------------
    # Round to nearest rupee
    # -----------------------------

    return round(fare)


# ---------------------------------------------------------
# Calculate fares for every class
# ---------------------------------------------------------

def calculate_all_fares(
    distance_km,
    train_type="NORMAL"
):
    """
    Calculate fares for all available classes.

    Returns a dictionary like:

    {
        "SL": 500,
        "3A": 900,
        "2A": 1250,
        "1A": 1750
    }
    """

    fares = {}

    for travel_class in CLASS_MULTIPLIER:

        fares[travel_class] = calculate_fare(
            distance_km,
            travel_class,
            train_type
        )

    return fares


# ---------------------------------------------------------
# Calculate average speed
# ---------------------------------------------------------

def calculate_average_speed(
    distance_km,
    duration_minutes
):
    """
    Calculate average train speed in km/h.

    Example:

    300 km / 180 minutes
    = 100 km/h
    """

    try:
        distance_km = float(distance_km)
        duration_minutes = float(duration_minutes)
    except (TypeError, ValueError):
        raise ValueError(
            "Distance and duration must be numbers."
        )

    if distance_km <= 0:
        raise ValueError(
            "Distance must be greater than 0."
        )

    if duration_minutes <= 0:
        raise ValueError(
            "Duration must be greater than 0."
        )

    duration_hours = duration_minutes / 60

    return round(
        distance_km / duration_hours,
        2
    )


# ---------------------------------------------------------
# Determine train category from average speed
# ---------------------------------------------------------

def determine_train_type(average_speed):
    """
    Determine a basic train category from average speed.

    These thresholds are prototype rules and can be
    refined later.
    """

    try:
        average_speed = float(average_speed)
    except (TypeError, ValueError):
        raise ValueError(
            "Average speed must be a number."
        )

    if average_speed <= 0:
        return "NORMAL"

    if average_speed >= 90:
        return "SUPERFAST"

    if average_speed >= 70:
        return "EXPRESS"

    return "NORMAL"