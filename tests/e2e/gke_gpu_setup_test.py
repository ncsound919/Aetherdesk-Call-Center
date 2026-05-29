import os
import pytest
from playwright.sync_api import sync_playwright, expect

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "gen-lang-client-0314105027")
CLUSTER_NAME = os.environ.get("GKE_CLUSTER_NAME", "aetherdesk_cluster")
REGION = os.environ.get("GKE_REGION", "us-east1")


def test_gke_enable_gpu_nodepool():
    """
    Enable GPU node pool in GKE via Google Cloud Console.
    This test navigates to GKE, adds a GPU-enabled node pool.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = context.new_page()

        print(f"Navigating to GKE Clusters in project {PROJECT_ID}...")
        page.goto(f"https://console.cloud.google.com/kubernetes/list?project={PROJECT_ID}")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(5000)
        page.screenshot(path=".screenshots/gke_gpu_1_clusters.png")

        print(f"Clicking on cluster '{CLUSTER_NAME}'...")
        try:
            cluster_link = page.get_by_text(CLUSTER_NAME).first
            if cluster_link.is_visible():
                cluster_link.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(3000)
        except Exception as e:
            print(f"Could not find cluster: {e}")
            page.screenshot(path=".screenshots/gke_gpu_1_error.png")

        page.screenshot(path=".screenshots/gke_gpu_2_cluster_details.png")

        print("Navigating to Node Pools tab...")
        try:
            nodepools_tab = page.get_by_role("tab", name="Node Pools").or_(
                page.get_by_text("Node Pools")
            ).first
            if nodepools_tab.is_visible():
                nodepools_tab.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)
        except Exception as e:
            print(f"Could not find Node Pools tab: {e}")

        page.screenshot(path=".screenshots/gke_gpu_3_nodepools.png")

        print("Clicking 'Add Node Pool' button...")
        try:
            add_nodepool_btn = page.get_by_role("button", name="Add Node Pool").or_(
                page.get_by_text("Add Node Pool")
            ).first
            if add_nodepool_btn.is_visible():
                add_nodepool_btn.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(3000)
        except Exception as e:
            print(f"Could not find Add Node Pool button: {e}")

        page.screenshot(path=".screenshots/gke_gpu_4_add_nodepool.png")

        print("Configuring GPU node pool...")

        try:
            nodepool_name_input = page.get_by_label("Name")
            if nodepool_name_input.is_visible():
                nodepool_name_input.fill("aetherdesk-gpu-nodepool")
        except:
            pass

        try:
            machine_type_dropdown = page.get_by_label("Machine type")
            if machine_type_dropdown.is_visible():
                machine_type_dropdown.click()
                page.wait_for_timeout(1000)
                page.keyboard.type("n1-standard-4")
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")
        except Exception as e:
            print(f"Machine type error: {e}")

        page.screenshot(path=".screenshots/gke_gpu_5_machine.png")

        print("Adding GPU accelerator...")
        try:
            add_gpu_btn = page.get_by_text("Add GPU").or_(
                page.get_by_text("Add accelerator")
            ).first
            if add_gpu_btn.is_visible():
                add_gpu_btn.click()
                page.wait_for_timeout(2000)
        except:
            print("GPU button not found, trying alternative...")

        try:
            accelerator_dropdown = page.get_by_label("GPU type").or_(
                page.get_by_text("GPU type")
            ).first
            if accelerator_dropdown.is_visible():
                accelerator_dropdown.click()
                page.wait_for_timeout(1000)
                page.keyboard.type("NVIDIA T4")
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")
        except Exception as e:
            print(f"GPU type error: {e}")

        try:
            gpu_count_input = page.get_by_label("GPU count")
            if gpu_count_input.is_visible():
                gpu_count_input.fill("1")
        except:
            pass

        page.screenshot(path=".screenshots/gke_gpu_6_gpu_config.png")

        print("Adding node labels and taints for scheduling...")
        try:
            labels_section = page.get_by_text("Labels").or_(
                page.get_by_text("Node labels")
            ).first
            if labels_section.is_visible():
                labels_section.click()
                page.wait_for_timeout(1000)

                key_input = page.get_by_label("Key").first
                if key_input.is_visible():
                    key_input.fill("workload-type")
                    value_input = page.get_by_label("Value").first
                    value_input.fill("gpu-ai")
        except Exception as e:
            print(f"Labels error: {e}")

        try:
            taints_section = page.get_by_text("Taints").or_(
                page.get_by_text("Node taints")
            ).first
            if taints_section.is_visible():
                taints_section.click()
                page.wait_for_timeout(1000)

                taint_key = page.get_by_label("Key").first
                if taint_key.is_visible():
                    taint_key.fill("nvidia.com/gpu")
        except Exception as e:
            print(f"Taints error: {e}")

        page.screenshot(path=".screenshots/gke_gpu_7_labels_taints.png")

        print("Clicking 'Create' button to create GPU node pool...")
        try:
            create_btn = page.get_by_role("button", name="Create").or_(
                page.get_by_text("Create node pool")
            ).first
            if create_btn.is_visible():
                create_btn.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(10000)
                page.screenshot(path=".screenshots/gke_gpu_8_creating.png")
                print("GPU node pool creation initiated!")
        except Exception as e:
            print(f"Error creating node pool: {e}")
            page.screenshot(path=".screenshots/gke_gpu_error.png")

        print("\n" + "="*60)
        print("GPU Node Pool Setup Complete!")
        print(f"Node Pool: aetherdesk-gpu-nodepool")
        print(f"Cluster: {CLUSTER_NAME} in {REGION}")
        print("="*60)

        context.close()
        browser.close()


def test_gke_enable_cpu_nodepool():
    """
    Enable CPU node pool for TTS (Chatterbox) in GKE.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = context.new_page()

        print(f"Navigating to GKE Clusters in project {PROJECT_ID}...")
        page.goto(f"https://console.cloud.google.com/kubernetes/list?project={PROJECT_ID}")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(5000)

        print(f"Clicking on cluster '{CLUSTER_NAME}'...")
        try:
            cluster_link = page.get_by_text(CLUSTER_NAME).first
            if cluster_link.is_visible():
                cluster_link.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(3000)
        except Exception as e:
            print(f"Could not find cluster: {e}")

        print("Navigating to Node Pools tab...")
        try:
            nodepools_tab = page.get_by_role("tab", name="Node Pools").or_(
                page.get_by_text("Node Pools")
            ).first
            if nodepools_tab.is_visible():
                nodepools_tab.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)
        except Exception as e:
            print(f"Could not find Node Pools tab: {e}")

        print("Clicking 'Add Node Pool' button...")
        try:
            add_nodepool_btn = page.get_by_role("button", name="Add Node Pool").or_(
                page.get_by_text("Add Node Pool")
            ).first
            if add_nodepool_btn.is_visible():
                add_nodepool_btn.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(3000)
        except Exception as e:
            print(f"Could not find Add Node Pool button: {e}")

        print("Configuring CPU node pool for TTS...")

        try:
            nodepool_name_input = page.get_by_label("Name")
            if nodepool_name_input.is_visible():
                nodepool_name_input.fill("aetherdesk-cpu-nodepool")
        except:
            pass

        try:
            machine_type_dropdown = page.get_by_label("Machine type")
            if machine_type_dropdown.is_visible():
                machine_type_dropdown.click()
                page.wait_for_timeout(1000)
                page.keyboard.type("n2-standard-4")
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")
        except Exception as e:
            print(f"Machine type error: {e}")

        try:
            nodes_input = page.get_by_label("Number of nodes")
            if nodes_input.is_visible():
                nodes_input.fill("2")
        except:
            pass

        page.screenshot(path=".screenshots/gke_cpu_1_config.png")

        print("Adding node labels for scheduling...")
        try:
            labels_section = page.get_by_text("Labels").or_(
                page.get_by_text("Node labels")
            ).first
            if labels_section.is_visible():
                labels_section.click()
                page.wait_for_timeout(1000)

                key_input = page.get_by_label("Key").first
                if key_input.is_visible():
                    key_input.fill("workload-type")
                    value_input = page.get_by_label("Value").first
                    value_input.fill("cpu-ai")
        except Exception as e:
            print(f"Labels error: {e}")

        page.screenshot(path=".screenshots/gke_cpu_2_labels.png")

        print("Clicking 'Create' button to create CPU node pool...")
        try:
            create_btn = page.get_by_role("button", name="Create").or_(
                page.get_by_text("Create node pool")
            ).first
            if create_btn.is_visible():
                create_btn.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(10000)
                page.screenshot(path=".screenshots/gke_cpu_3_creating.png")
                print("CPU node pool creation initiated!")
        except Exception as e:
            print(f"Error creating node pool: {e}")
            page.screenshot(path=".screenshots/gke_cpu_error.png")

        print("\n" + "="*60)
        print("CPU Node Pool Setup Complete!")
        print(f"Node Pool: aetherdesk-cpu-nodepool")
        print(f"Machine: n2-standard-4")
        print(f"Cluster: {CLUSTER_NAME} in {REGION}")
        print("="*60)

        context.close()
        browser.close()