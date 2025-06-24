from utils import logger

def main():
    ui_logger = logger.ui_logger
    ui_logger.info("Starting the main function.")
    ui_logger.error("Starting the main function.")

if __name__ == "__main__":
    main()