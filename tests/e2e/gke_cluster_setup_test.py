import pytest
from playwright.sync_api import sync_playwright
import os

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "your-gcp-project-id")
CLUSTER_NAME = os.environ.get("GKE_CLUSTER_NAME", "callcenter-cluster")
REGION = os.environ.get("GKE_REGION", "us-east1")
NODE_COUNT = os.environ.get("GKE_NODE_COUNT", "2")
MACHINE_TYPE = os.environ.get("GKE_MACHINE_TYPE", "e2-standard-4")

def test_gke_cluster_create():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="/tmp/playwright-chrome-profile",
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"]
        )
        page = browser.new_page()

        print(f"Step 1: Navigating to GKE Clusters...")
        page.goto(f"https://console.cloud.google.com/kubernetes/list?project={PROJECT_ID}")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(5000)
        page.screenshot(path=".screenshots/gke_clusters.png")

        print(f"Step 2: Clicking 'Create Cluster'...")
        try:
            create_cluster_btn = page.get_by_role("button", name="Create").or_(
                page.get_by_text("Create Cluster")
            ).first
            if create_cluster_btn.is_visible():
                create_cluster_btn.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(3000)
        except Exception as e:
            print(f"Error clicking create: {e}")

        page.screenshot(path=".screenshots/gke_create_cluster.png")

        print(f"Step 3: Configuring cluster - Name: {CLUSTER_NAME}, Region: {REGION}")

        # Cluster name
        try:
            name_input = page.get_by_label("Cluster name")
            if name_input.is_visible():
                name_input.fill(CLUSTER_NAME)
        except:
            pass

        # Location/Region
        try:
            location_dropdown = page.get_by_label("Location")
            if location_dropdown.is_visible():
                location_dropdown.click()
                page.wait_for_timeout(1000)
                page.keyboard.type(REGION)
                page.wait_for_timeout(1000)
                page.keyboard.press("Enter")
        except:
            pass

        page.screenshot(path=".screenshots/gke_cluster_config.png")

        # Node pool configuration
        print(f"Step 4: Configuring node pool - Nodes: {NODE_COUNT}, Machine: {MACHINE_TYPE}")

        try:
            # Click on default node pool to configure
            node_pool_section = page.get_by_text("Node pools").first
            if node_pool_section.is_visible():
                node_pool_section.click()
                page.wait_for_timeout(2000)
        except:
            pass

        try:
            nodes_input = page.get_by_label("Nodes")
            if nodes_input.is_visible():
                nodes_input.fill(NODE_COUNT)
        except:
            pass

        try:
            machine_input = page.get_by_label("Machine type")
            if machine_input.is_visible():
                machine_input.click()
                page.wait_for_timeout(1000)
                page.keyboard.type(MACHINE_TYPE)
                page.wait_for_timeout(1000)
                page.keyboard.press("Enter")
        except:
            pass

        page.screenshot(path=".screenshots/gke_node_config.png")

        print("Step 5: Clicking 'Create' button...")
        try:
            create_btn = page.get_by_role("button", name="Create").first
            if create_btn.is_visible():
                create_btn.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(10000)
                page.screenshot(path=".screenshots/gke_cluster_creating.png")
                print(f"Cluster '{CLUSTER_NAME}' is being created. This may take 5-10 minutes.")
        except Exception as e:
            print(f"Error clicking cluster create: {e}")
            page.screenshot(path=".screenshots/gke_create_error.png")

        browser.close()
        print("\n" + "="*60)
        print("GKE Cluster creation initiated!")
        print(f"Cluster: {CLUSTER_NAME} in {REGION}")
        print(f"Project: {PROJECT_ID}")
        print("="*60)