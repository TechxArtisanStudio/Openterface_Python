import logging

def setup_logger(name, level=logging.INFO, log_file=None):
    """
    Set up a logger with the specified name and logging level.
    Optionally log to a file.
    
    Args:
        name (str): The name of the logger.
        level (int): The logging level (default is logging.INFO).
        log_file (str, optional): Path to log file. If provided, logs will be written to this file.
    
    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Create formatter and add it to the handler
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')


    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    # Add the handler to the logger
    logger.addHandler(ch)

    if log_file:
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    
    return logger

ui_logger = setup_logger("opf.ui", logging.INFO)
core_logger = setup_logger("opf.core", logging.INFO)
serial_logger = setup_logger("opf.serial", logging.INFO)
