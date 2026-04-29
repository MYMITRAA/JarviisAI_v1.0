import logging

def configure_logging(service_name=None, level="INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=f"%(asctime)s - {service_name} - %(levelname)s - %(message)s",
    )